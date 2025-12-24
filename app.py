import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
import time
import plotly.express as px
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Radar BI v2.1 - PureHome", layout="wide", page_icon="📈")

# --- NORMALIZAÇÃO ---
def normalizar_concorrente(nome):
    nome = re.sub(r'\s*\(\d+\)\s*', '', str(nome))
    return nome.strip().upper()

# --- LOGIN ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]: return True
    st.markdown("<h1 style='text-align: center;'>💎 Radar PureHome</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.subheader("Acesso Restrito")
            user = st.text_input("Usuário")
            pw = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                if user == st.secrets["credentials"]["usuario"] and pw == st.secrets["credentials"]["senha"]:
                    st.session_state["password_correct"] = True
                    st.rerun()
                else: st.error("😕 Senha incorreta.")
        return False

if check_password():
    @st.cache_resource
    def init_connection():
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

    supabase = init_connection()

    def busca_dados_completos():
        todos = []
        offset = 0
        while True:
            res = supabase.table('historico_concorrentes').select("*").range(offset, offset + 999).execute()
            if not res.data: break
            todos.extend(res.data)
            offset += 1000
            if len(res.data) < 1000: break
        df = pd.DataFrame(todos)
        if not df.empty: df['concorrente'] = df['concorrente'].apply(normalizar_concorrente)
        return df

    # --- SIDEBAR ---
    with st.sidebar:
        st.title("⚙️ Painel Pro")
        if st.button("🚪 Sair"):
            del st.session_state["password_correct"]
            st.rerun()
        st.divider()
        st.subheader("📤 Upload")
        up_file = st.file_uploader("Planilha", type=["xlsx", "csv"])
        d_ref = st.date_input("Data", datetime.now())
        c_in = st.text_input("Concorrente")
        if st.button("💾 Salvar Dados"):
            if up_file and c_in:
                df_up = pd.read_excel(up_file) if up_file.name.endswith('xlsx') else pd.read_csv(up_file)
                dados = []
                for _, r in df_up.iterrows():
                    dados.append({
                        "data_registro": str(d_ref), "concorrente": normalizar_concorrente(c_in),
                        "titulo": str(r.get('Título', ''))[:200], "gtin": str(r.get('GTIN', '')).replace('.0', '').strip(),
                        "marca": str(r.get('Marca', '')), "preco": float(pd.to_numeric(r.get('Preço Médio'), errors='coerce') or 0),
                        "estoque": int(pd.to_numeric(r.get('Estoque'), errors='coerce') or 0),
                        "vendas_unid": int(pd.to_numeric(r.get('Vendas em Unid.'), errors='coerce') or 0)
                    })
                for i in range(0, len(dados), 1000): supabase.table('historico_concorrentes').insert(dados[i:i+1000]).execute()
                st.success("✅ Ok!"); time.sleep(1); st.rerun()

    # ==============================================================================
    # PROCESSAMENTO DE DADOS
    # ==============================================================================
    df_g = busca_dados_completos()
    
    if not df_g.empty:
        df_g['data_registro'] = pd.to_datetime(df_g['data_registro']).dt.date
        datas = sorted(df_g['data_registro'].unique(), reverse=True)
        dt_hj, dt_ant = datas[0], datas[1] if len(datas) > 1 else datas[0]
        
        df_hj = df_g[df_g['data_registro'] == dt_hj]
        df_at = df_g[df_g['data_registro'] == dt_ant]

        # Lógica de Ruptura e Reposição
        df_r_hj = df_hj.set_index(['gtin', 'concorrente'])
        df_r_ant = df_at.set_index(['gtin', 'concorrente'])
        
        zerados = df_hj[df_hj['estoque'] == 0]
        repostos = df_r_hj[(df_r_hj['estoque'] > 0) & (df_r_ant['estoque'] == 0)].reset_index()

        # NAVEGAÇÃO
        tabs = st.tabs(["📊 Dashboard", "💰 Buy Box", "🤖 Inteligência de Compra", "📋 SKUs", "🚨 Rupturas", "🔍 Comparativo"])

        # --- ABA DASHBOARD ---
        with tabs[0]:
            st.subheader(f"📅 Analisando: {datas[-1].strftime('%d/%m/%Y')} ➔ {dt_hj.strftime('%d/%m/%Y')}")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("SKUs no Radar", len(df_hj))
            c2.metric("Zerados Hoje", len(zerados), delta=f"{len(zerados)} itens", delta_color="inverse")
            c3.metric("Repostos (Voltaram)", len(repostos))
            c4.metric("Faturamento Estimado", f"R$ {(df_hj['vendas_unid']*df_hj['preco']).sum():,.2f}")
            
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                f_m = df_hj.groupby('marca').apply(lambda x: (x['vendas_unid']*x['preco']).sum()).sort_values(ascending=False).head(10).reset_index(name='fat')
                st.plotly_chart(px.bar(f_m, x='marca', y='fat', title="Top 10 Marcas (Faturamento)", text_auto='.2s', color='fat', color_continuous_scale='Greens'), use_container_width=True)
            with col2:
                f_c = df_g.groupby(['data_registro','concorrente']).apply(lambda x: (x['vendas_unid']*x['preco']).sum()).reset_index(name='fat')
                st.plotly_chart(px.line(f_c, x='data_registro', y='fat', color='concorrente', title="Market Share Diário"), use_container_width=True)

        # --- ABA BUY BOX ---
        with tabs[1]:
            st.header("🎯 Sugestão de Preço (- R$ 1,00)")
            df_bb = df_hj[df_hj['preco'] > 0].groupby(['gtin', 'titulo']).agg({'preco': 'min', 'concorrente': 'first'}).reset_index()
            df_bb['Preço Sugerido'] = df_bb['preco'] - 1.0
            st.dataframe(df_bb.rename(columns={'titulo': 'Produto', 'preco': 'Menor Preço', 'concorrente': 'Líder'}).style.format({'Menor Preço': 'R$ {:.2f}', 'Preço Sugerido': 'R$ {:.2f}'}), use_container_width=True)

        # --- ABA IA DE COMPRA ---
        with tabs[2]:
            st.header("🤖 Projeção de Estoque e Compra")
            # Média de vendas por dia (considerando dias com registro)
            num_dias = len(datas)
            df_ia = df_hj.groupby(['gtin', 'titulo', 'marca']).agg({'vendas_unid': 'sum', 'estoque': 'sum', 'preco': 'mean'}).reset_index()
            df_ia['Venda Média Dia'] = df_ia['vendas_unid'] / num_dias
            df_ia['Dias de Estoque'] = df_ia.apply(lambda x: x['estoque'] / x['Venda Média Dia'] if x['Venda Média Dia'] > 0 else 999, axis=1)
            
            def analisar_status(row):
                if row['Dias de Estoque'] < 7: return "🚨 COMPRA URGENTE"
                if row['Dias de Estoque'] < 15: return "⚠️ REPOR EM BREVE"
                if row['Dias de Estoque'] > 60: return "🔥 QUEIMA DE ESTOQUE"
                return "✅ ESTÁVEL"

            df_ia['Status IA'] = df_ia.apply(analisar_status, axis=1)
            st.dataframe(df_ia.sort_values('vendas_unid', ascending=False).style.format({'Venda Média Dia': '{:.1f}', 'Dias de Estoque': '{:.0f} dias', 'preco': 'R$ {:.2f}'}), use_container_width=True)

        # --- ABA SKUs ---
        with tabs[3]:
            search = st.text_input("🔍 Buscar Produto")
            df_s = df_hj.sort_values('vendas_unid', ascending=False)
            if search: df_s = df_s[df_s['titulo'].str.contains(search, case=False)]
            st.dataframe(df_s[['vendas_unid','titulo','concorrente','preco','estoque']], use_container_width=True)

        # --- ABA RUPTURAS ---
        with tabs[4]:
            col_z, col_r = st.columns(2)
            with col_z:
                st.subheader(f"❌ Zerados Agora ({len(zerados)})")
                st.dataframe(zerados[['concorrente','titulo','vendas_unid']].sort_values('vendas_unid', ascending=False), use_container_width=True)
            with col_r:
                st.subheader(f"✅ Repostos ({len(repostos)})")
                st.dataframe(repostos[['concorrente','titulo','estoque_hj','vendas_unid_hj']].rename(columns={'estoque_hj': 'Estoque', 'vendas_unid_hj': 'Vendas'}), use_container_width=True)

        # --- ABA COMPARATIVO (RESTAURADO) ---
        with tabs[5]:
            st.header("🔍 Comparativo de Preços e Variação")
            c_c1, c_c2 = st.columns(2)
            with c_c1: s_hj = st.selectbox("Data Atual", datas, index=0)
            with c_c2: s_ant = st.selectbox("Data Anterior", datas, index=min(1, len(datas)-1))
            
            df_a = df_g[df_g['data_registro'] == s_hj].set_index(['gtin','concorrente'])
            df_b = df_g[df_g['data_registro'] == s_ant].set_index(['gtin','concorrente'])
            res = df_a.join(df_b, lsuffix='_hj', rsuffix='_ant', how='inner').reset_index()
            
            res['var_abs'] = res['preco_hj'] - res['preco_ant']
            res['var_pct'] = ((res['preco_hj'] - res['preco_ant']) / res['preco_ant']) * 100
            
            df_final = res[['concorrente','titulo_hj','preco_ant','preco_hj','var_pct','estoque_hj']].rename(columns={'titulo_hj': 'Produto', 'preco_ant': 'P. Ant', 'preco_hj': 'P. Hj', 'var_pct': '% Var', 'estoque_hj': 'Estoque'})
            
            st.dataframe(
                df_final.sort_values('% Var', ascending=False)
                .style.format({'P. Ant': 'R$ {:.2f}', 'P. Hj': 'R$ {:.2f}', '% Var': '{:+.2f}%'})
                .map(lambda x: 'color: green' if x > 0 else ('color: red' if x < 0 else 'color: gray'), subset=['% Var']),
                use_container_width=True
            )
