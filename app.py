import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime
import time
import plotly.express as px
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Radar BI v2.3.2 - PureHome", layout="wide", page_icon="📈")

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
                else: st.error("😕 Credenciais incorretas.")
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
        st.title("⚙️ Painel Admin")
        if st.button("🚪 Sair"):
            del st.session_state["password_correct"]
            st.rerun()
        st.divider()
        st.subheader("📤 Upload")
        up_file = st.file_uploader("Arquivo", type=["xlsx", "csv"])
        d_ref = st.date_input("Data", datetime.now())
        c_in = st.text_input("Concorrente")
        if st.button("💾 Salvar"):
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
                st.success("✅ Salvo!"); time.sleep(1); st.rerun()

    # --- PROCESSAMENTO GLOBAL ---
    df_g = busca_dados_completos()
    
    if not df_g.empty:
        df_g['data_registro'] = pd.to_datetime(df_g['data_registro']).dt.date
        datas = sorted(df_g['data_registro'].unique(), reverse=True)
        dt_hj = datas[0]
        dt_ant = datas[1] if len(datas) > 1 else dt_hj

        # NAVEGAÇÃO
        tabs = st.tabs(["📊 Dashboard", "💰 Buy Box", "🤖 Inteligência de Compra", "📋 SKUs", "🚨 Rupturas", "🔍 Comparativo"])

        # --- ABA 1: DASHBOARD (COM FILTRO) ---
        with tabs[0]:
            st.header("📊 Inteligência de Mercado")
            
            # SELETOR DE MODO
            modo_visao = st.radio("Período de análise:", ["Último Dia (Hoje)", "Todo o Período (Acumulado)"], horizontal=True)
            
            if modo_visao == "Último Dia (Hoje)":
                df_dash = df_g[df_g['data_registro'] == dt_hj].copy()
                msg_periodo = f"Exibindo apenas: {dt_hj.strftime('%d/%m/%Y')}"
            else:
                df_dash = df_g.copy()
                msg_periodo = f"Acumulado de {datas[-1].strftime('%d/%m/%Y')} até {dt_hj.strftime('%d/%m/%Y')}"

            st.caption(f"📅 {msg_periodo}")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("SKUs no Radar", len(df_dash['gtin'].unique()))
            fat_val = (df_dash['vendas_unid'] * df_dash['preco']).sum()
            c2.metric("Faturamento", f"R$ {fat_val:,.2f}")
            c3.metric("Ticket Médio", f"R$ {df_dash['preco'].mean():.2f}")
            c4.metric("Itens s/ Estoque", len(df_dash[df_dash['estoque'] == 0]))
            
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                df_dash['fat_item'] = df_dash['vendas_unid'] * df_dash['preco']
                f_m = df_dash.groupby('marca')['fat_item'].sum().sort_values(ascending=False).head(10).reset_index()
                st.plotly_chart(px.bar(f_m, x='marca', y='fat_item', title=f"Top 10 Marcas ({modo_visao})", text_auto='.2s', color='fat_item', color_continuous_scale='Greens'), use_container_width=True)
            with col2:
                df_g['fat_diario'] = df_g['vendas_unid'] * df_g['preco']
                f_c = df_g.groupby(['data_registro','concorrente'])['fat_diario'].sum().reset_index()
                st.plotly_chart(px.line(f_c, x='data_registro', y='fat_diario', color='concorrente', title="Market Share Histórico", markers=True), use_container_width=True)

        # --- ABA 2: BUY BOX ---
        with tabs[1]:
            st.header("🎯 Sugestão de Preço (- R$ 1,00)")
            df_hj_bb = df_g[df_g['data_registro'] == dt_hj]
            df_bb = df_hj_bb[df_hj_bb['preco'] > 0].groupby(['gtin', 'titulo']).agg({'preco': 'min', 'concorrente': 'first'}).reset_index()
            df_bb['Sugerido'] = df_bb['preco'] - 1.0
            st.dataframe(df_bb.rename(columns={'titulo': 'Produto', 'preco': 'Menor Preço', 'concorrente': 'Líder'}).style.format({'Menor Preço': 'R$ {:.2f}', 'Sugerido': 'R$ {:.2f}'}), use_container_width=True)

        # --- ABA 3: INTELIGÊNCIA DE COMPRA ---
        with tabs[2]:
            st.header("🤖 Projeção de Estoque")
            df_hj_ia = df_g[df_g['data_registro'] == dt_hj]
            num_dias = len(datas)
            df_ia = df_hj_ia.groupby(['gtin', 'titulo', 'marca']).agg({'vendas_unid': 'sum', 'estoque': 'sum', 'preco': 'min'}).reset_index()
            df_ia['Venda/Dia'] = df_ia['vendas_unid'] / num_dias
            df_ia['Dias Estoque'] = df_ia.apply(lambda x: x['estoque'] / x['Venda/Dia'] if x['Venda/Dia'] > 0 else 999, axis=1)
            
            def status_ia(row):
                if row['Dias Estoque'] < 7: return "🚨 COMPRA URGENTE"
                if row['Dias Estoque'] < 15: return "⚠️ REPOR BREVE"
                if row['Dias Estoque'] > 60: return "🔥 QUEIMA / LENTO"
                return "✅ ESTÁVEL"
            
            df_ia['Sugestão'] = df_ia.apply(status_ia, axis=1)
            
            resumo_ia = df_ia['Sugestão'].value_counts()
            c_ia1, c_ia2, c_ia3, c_ia4 = st.columns(4)
            c_ia1.metric("🚨 Urgentes", resumo_ia.get("🚨 COMPRA URGENTE", 0))
            c_ia2.metric("⚠️ Repor", resumo_ia.get("⚠️ REPOR BREVE", 0))
            c_ia3.metric("✅ Estáveis", resumo_ia.get("✅ ESTÁVEL", 0))
            c_ia4.metric("🔥 Queima", resumo_ia.get("🔥 QUEIMA / LENTO", 0))
            
            st.divider()
            filtro_acao = st.multiselect("Filtrar por Status", ["🚨 COMPRA URGENTE", "⚠️ REPOR BREVE", "✅ ESTÁVEL", "🔥 QUEIMA / LENTO"], default=["🚨 COMPRA URGENTE", "⚠️ REPOR BREVE"])
            df_ia_f = df_ia[df_ia['Sugestão'].isin(filtro_acao)].sort_values(['Sugestão', 'vendas_unid'], ascending=[True, False])
            st.dataframe(df_ia_f[['Sugestão', 'titulo', 'marca', 'vendas_unid', 'estoque', 'preco', 'Venda/Dia', 'Dias Estoque']].rename(columns={'titulo': 'Produto', 'preco': 'Menor Preço Mercado'}).style.format({'Menor Preço Mercado': 'R$ {:.2f}', 'Venda/Dia': '{:.1f}', 'Dias Estoque': '{:.0f} dias'}).map(lambda x: 'background-color: #f8d7da; font-weight: bold' if x == "🚨 COMPRA URGENTE" else ('background-color: #fff3cd' if x == "⚠️ REPOR BREVE" else ''), subset=['Sugestão']), use_container_width=True)

        # --- ABA 4: SKUs ---
        with tabs[3]:
            search = st.text_input("🔍 Buscar Produto")
            df_s = df_g[df_g['data_registro'] == dt_hj].sort_values('vendas_unid', ascending=False)
            if search: df_s = df_s[df_s['titulo'].str.contains(search, case=False)]
            st.dataframe(df_s[['vendas_unid','titulo','concorrente','preco','estoque']], use_container_width=True)

        # --- ABA 5: RUPTURAS ---
        with tabs[4]:
            df_hj_r = df_g[df_g['data_registro'] == dt_hj].copy()
            df_at_r = df_g[df_g['data_registro'] == dt_ant].copy()
            df_c_r = df_hj_r[['gtin','concorrente','estoque']].merge(df_at_r[['gtin','concorrente','estoque']], on=['gtin','concorrente'], suffixes=('_hj','_ant'), how='inner')
            repostos = df_c_r[(df_c_r['estoque_hj'] > 0) & (df_c_r['estoque_ant'] == 0)].merge(df_hj_r[['gtin','concorrente','titulo','preco']], on=['gtin','concorrente'])
            zerados = df_hj_r[df_hj_r['estoque'] == 0]
            
            col_z, col_r = st.columns(2)
            with col_z:
                st.subheader(f"❌ Zerados ({len(zerados)})")
                st.dataframe(zerados[['concorrente','titulo','vendas_unid']].sort_values('vendas_unid', ascending=False), use_container_width=True)
            with col_r:
                st.subheader(f"✅ Repostos ({len(repostos)})")
                st.dataframe(repostos[['concorrente','titulo','estoque_hj','preco']].rename(columns={'estoque_hj':'Estoque'}), use_container_width=True)

        # --- ABA 6: COMPARATIVO ---
        with tabs[5]:
            st.header("🔍 Comparativo Diário")
            c_c1, c_c2 = st.columns(2)
            with c_c1: s_hj = st.selectbox("Data Hoje", datas, index=0)
            with c_c2: s_ant = st.selectbox("Data Base", datas, index=min(1, len(datas)-1))
            df_a_c = df_g[df_g['data_registro'] == s_hj].set_index(['gtin','concorrente'])
            df_b_c = df_g[df_g['data_registro'] == s_ant].set_index(['gtin','concorrente'])
            res_c = df_a_c.join(df_b_c, lsuffix='_hj', rsuffix='_ant', how='inner').reset_index()
            res_c['var_pct'] = ((res_c['preco_hj'] - res_c['preco_ant']) / res_c['preco_ant']) * 100
            df_f_c = res_c[['concorrente','titulo_hj','preco_ant','preco_hj','var_pct','estoque_hj']].rename(columns={'titulo_hj':'Produto','preco_ant':'Ant.','preco_hj':'Hj','var_pct':'% Var'})
            st.dataframe(df_f_c.sort_values('% Var', ascending=False).style.format({'Ant.':'R$ {:.2f}','Hj':'R$ {:.2f}','% Var':'{:+.2f}%'}).map(lambda x: 'color: green' if x > 0 else ('color: red' if x < 0 else 'color: gray'), subset=['% Var']), use_container_width=True)
    else:
        st.info("Aguardando upload de dados...")
