import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime
import time
import plotly.express as px
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Radar BI v2.3.3", layout="wide", page_icon="📈")

# --- LOGIN ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]: return True
    st.markdown("<h1 style='text-align: center;'>💎 Radar PureHome</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            user = st.text_input("Usuário")
            pw = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                if user == st.secrets["credentials"]["usuario"] and pw == st.secrets["credentials"]["senha"]:
                    st.session_state["password_correct"] = True
                    st.rerun()
                else: st.error("Incorreto")
        return False

if check_password():
    @st.cache_resource
    def init_connection():
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    supabase = init_connection()

    def busca_dados():
        todos = []
        offset = 0
        while True:
            res = supabase.table('historico_concorrentes').select("*").range(offset, offset + 999).execute()
            if not res.data: break
            todos.extend(res.data)
            offset += 1000
            if len(res.data) < 1000: break
        df = pd.DataFrame(todos)
        if not df.empty:
            df['concorrente'] = df['concorrente'].apply(lambda x: re.sub(r'\s*\(\d+\)\s*', '', str(x)).strip().upper())
            df['data_registro'] = pd.to_datetime(df['data_registro']).dt.date
        return df

    # --- CARREGAMENTO ---
    df_g = busca_dados()

    with st.sidebar:
        st.title("⚙️ Painel")
        if st.button("🚪 Sair"):
            del st.session_state["password_correct"]
            st.rerun()
        st.divider()
        up_file = st.file_uploader("Upload Nubmetrics")
        d_ref = st.date_input("Data", datetime.now())
        c_in = st.text_input("Concorrente")
        if st.button("💾 Salvar"):
            if up_file and c_in:
                df_up = pd.read_excel(up_file) if up_file.name.endswith('xlsx') else pd.read_csv(up_file)
                dados = []
                for _, r in df_up.iterrows():
                    dados.append({
                        "data_registro": str(d_ref), "concorrente": c_in.strip().upper(),
                        "titulo": str(r.get('Título', ''))[:200], "gtin": str(r.get('GTIN', '')).replace('.0', '').strip(),
                        "marca": str(r.get('Marca', '')), "preco": float(pd.to_numeric(r.get('Preço Médio'), errors='coerce') or 0),
                        "estoque": int(pd.to_numeric(r.get('Estoque'), errors='coerce') or 0),
                        "vendas_unid": int(pd.to_numeric(r.get('Vendas em Unid.'), errors='coerce') or 0)
                    })
                for i in range(0, len(dados), 1000): supabase.table('historico_concorrentes').insert(dados[i:i+1000]).execute()
                st.success("Salvo!"); time.sleep(1); st.rerun()

    if not df_g.empty:
        datas = sorted(df_g['data_registro'].unique(), reverse=True)
        dt_hj = datas[0]
        dt_ant = datas[1] if len(datas) > 1 else dt_hj

        # --- NAVEGAÇÃO ---
        t1, t2, t3, t4, t5, t6 = st.tabs(["📊 Dashboard", "💰 Buy Box", "🤖 Inteligência de Compra", "📋 SKUs", "🚨 Rupturas", "🔍 Comparativo"])

        # --- ABA 1: DASHBOARD ---
        with t1:
            st.title("📊 Resumo Executivo")
            
            # FILTRO DE PERÍODO (POSIÇÃO CORRIGIDA)
            modo = st.radio("Selecione a abrangência dos dados:", ["Apenas Hoje", "Período Acumulado"], horizontal=True, key="filtro_dashboard")
            
            if modo == "Apenas Hoje":
                df_d = df_g[df_g['data_registro'] == dt_hj].copy()
                st.info(f"Mostrando dados de {dt_hj.strftime('%d/%m/%Y')}")
            else:
                df_d = df_g.copy()
                st.info(f"Mostrando acumulado de {datas[-1].strftime('%d/%m/%Y')} até {dt_hj.strftime('%d/%m/%Y')}")

            # KPIs
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("SKUs", len(df_d['gtin'].unique()))
            fat = (df_d['vendas_unid'] * df_d['preco']).sum()
            c2.metric("Faturamento", f"R$ {fat:,.2f}")
            c3.metric("Ticket Médio", f"R$ {df_d['preco'].mean():.2f}")
            c4.metric("S/ Estoque", len(df_d[df_d['estoque'] == 0]))

            st.divider()
            col_a, col_b = st.columns(2)
            with col_a:
                df_d['faturamento'] = df_d['vendas_unid'] * df_d['preco']
                f_m = df_d.groupby('marca')['faturamento'].sum().sort_values(ascending=False).head(10).reset_index()
                st.plotly_chart(px.bar(f_m, x='marca', y='faturamento', title="Top Marcas", text_auto='.2s'), use_container_width=True)
            with col_b:
                df_g['fat_d'] = df_g['vendas_unid'] * df_g['preco']
                f_c = df_g.groupby(['data_registro','concorrente'])['fat_d'].sum().reset_index()
                st.plotly_chart(px.line(f_c, x='data_registro', y='fat_d', color='concorrente', title="Market Share"), use_container_width=True)

        # --- ABA 2: BUY BOX ---
        with t2:
            st.header("🎯 Buy Box (- R$ 1,00)")
            df_bb = df_g[df_g['data_registro'] == dt_hj].copy()
            df_bb = df_bb[df_bb['preco'] > 0].groupby(['gtin', 'titulo']).agg({'preco': 'min', 'concorrente': 'first'}).reset_index()
            df_bb['Sugerido'] = df_bb['preco'] - 1.0
            st.dataframe(df_bb.style.format({'preco': 'R$ {:.2f}', 'Sugerido': 'R$ {:.2f}'}), use_container_width=True)

        # --- ABA 3: IA DE COMPRA ---
        with t3:
            st.header("🤖 Sugestão de Compra")
            df_ia = df_g[df_g['data_registro'] == dt_hj].copy()
            df_ia = df_ia.groupby(['gtin', 'titulo', 'marca']).agg({'vendas_unid': 'sum', 'estoque': 'sum', 'preco': 'min'}).reset_index()
            df_ia['V/Dia'] = df_ia['vendas_unid'] / len(datas)
            df_ia['Dias'] = df_ia.apply(lambda x: x['estoque'] / x['V/Dia'] if x['V/Dia'] > 0 else 999, axis=1)
            def st_ia(r):
                if r['Dias'] < 7: return "🚨 COMPRA URGENTE"
                if r['Dias'] < 15: return "⚠️ REPOR"
                if r['Dias'] > 60: return "🔥 QUEIMA"
                return "✅ OK"
            df_ia['Sugestão'] = df_ia.apply(st_ia, axis=1)
            
            res_ia = df_ia['Sugestão'].value_counts()
            i1, i2, i3, i4 = st.columns(4)
            i1.metric("🚨 Urgentes", res_ia.get("🚨 COMPRA URGENTE", 0))
            i2.metric("⚠️ Repor", res_ia.get("⚠️ REPOR", 0))
            
            st.dataframe(df_ia.sort_values('vendas_unid', ascending=False).style.format({'preco': 'R$ {:.2f}', 'V/Dia': '{:.1f}', 'Dias': '{:.0f}'}), use_container_width=True)

        # --- ABA 4: SKUs ---
        with t4:
            df_sku = df_g[df_g['data_registro'] == dt_hj].copy()
            st.dataframe(df_sku[['vendas_unid','titulo','concorrente','preco','estoque']].sort_values('vendas_unid', ascending=False), use_container_width=True)

        # --- ABA 5: RUPTURAS ---
        with t5:
            d_h = df_g[df_g['data_registro'] == dt_hj].copy()
            d_a = df_g[df_g['data_registro'] == dt_ant].copy()
            df_c = d_h.merge(d_a, on=['gtin','concorrente'], suffixes=('_h','_a'), how='inner')
            rep = df_c[(df_c['estoque_h'] > 0) & (df_c['estoque_a'] == 0)]
            zer = d_h[d_h['estoque'] == 0]
            st.subheader(f"❌ Zerados ({len(zer)})")
            st.dataframe(zer, use_container_width=True)
            st.subheader(f"✅ Repostos ({len(rep)})")
            st.dataframe(rep, use_container_width=True)

        # --- ABA 6: COMPARATIVO ---
        with t6:
            st.header("🔍 Comparativo")
            c_a = st.selectbox("Data 1", datas, index=0)
            c_b = st.selectbox("Data 2", datas, index=min(1, len(datas)-1))
            res = df_g[df_g['data_registro'] == c_a].set_index(['gtin','concorrente']).join(df_g[df_g['data_registro'] == c_b].set_index(['gtin','concorrente']), lsuffix='_1', rsuffix='_2', how='inner').reset_index()
            res['%'] = ((res['preco_1'] - res['preco_2']) / res['preco_2']) * 100
            st.dataframe(res[['concorrente','titulo_1','preco_2','preco_1','%']].style.format({'preco_1': 'R$ {:.2f}', 'preco_2': 'R$ {:.2f}', '%': '{:+.2f}%'}), use_container_width=True)
    else:
        st.info("Sem dados.")
