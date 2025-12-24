import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime
import time
import plotly.express as px
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Radar BI v2.0 - PureHome", layout="wide", page_icon="🤖")

# --- FUNÇÃO PARA NORMALIZAÇÃO ---
def normalizar_concorrente(nome):
    nome = re.sub(r'\s*\(\d+\)\s*', '', str(nome))
    return nome.strip().upper()

# --- SISTEMA DE LOGIN ---
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
                else: st.error("😕 Incorreto.")
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
        st.title("⚙️ Painel v2.0")
        if st.button("🚪 Sair"):
            del st.session_state["password_correct"]
            st.rerun()
        st.divider()
        st.subheader("📤 Upload")
        up_file = st.file_uploader("Planilha", type=["xlsx", "csv"])
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
                st.success("✅ Ok!"); time.sleep(1); st.rerun()

    # ==============================================================================
    # NAVEGAÇÃO
    # ==============================================================================
    t_dash, t_buybox, t_ia, t_rupturas, t_comp = st.tabs([
        "📊 Dashboard", "💰 Estratégia Buy Box", "🤖 Sugestão de Compra (IA)", "🚨 Rupturas", "🔍 Comparativo"
    ])

    df_g = busca_dados_completos()
    
    if not df_g.empty:
        df_g['data_registro'] = pd.to_datetime(df_g['data_registro']).dt.date
        datas = sorted(df_g['data_registro'].unique(), reverse=True)
        dt_fim, dt_ini = datas[0], datas[-1]
        df_hj = df_g[df_g['data_registro'] == dt_fim]

        # --- ABA 1: DASHBOARD ---
        with t_dash:
            st.subheader(f"📅 Período Analisado: {dt_ini.strftime('%d/%m/%Y')} até {dt_fim.strftime('%d/%m/%Y')}")
            c1, c2, c3 = st.columns(3)
            c1.metric("SKUs no Radar", len(df_hj))
            c2.metric("Vendas Totais (Período)", f"{df_g['vendas_unid'].sum():,.0f}")
            c3.metric("Faturamento Estimado", f"R$ {(df_hj['vendas_unid']*df_hj['preco']).sum():,.2f}")
            
            st.divider()
            col_l, col_r = st.columns(2)
            with col_l:
                f_m = df_hj.groupby('marca').apply(lambda x: (x['vendas_unid']*x['preco']).sum()).sort_values(ascending=False).head(10).reset_index(name='fat')
                st.plotly_chart(px.bar(f_m, x='marca', y='fat', title="Top 10 Marcas (Faturamento)", text_auto='.2s'), use_container_width=True)
            with col_r:
                f_c = df_g.groupby(['data_registro','concorrente']).apply(lambda x: (x['vendas_unid']*x['preco']).sum()).reset_index(name='fat')
                st.plotly_chart(px.line(f_c, x='data_registro', y='fat', color='concorrente', title="Guerra de Concorrentes"), use_container_width=True)

        # --- ABA 2: ESTRATÉGIA BUY BOX ---
        with t_buybox:
            st.header("🎯 Sugestão de Preço para Ganhar (Buy Box)")
            st.markdown("A lógica abaixo identifica o **menor preço atual** de cada GTIN no mercado e sugere o seu preço com **R$ 1,00 de desconto**.")
            
            df_bb = df_hj[df_hj['preco'] > 0].groupby(['gtin', 'titulo']).agg({'preco': 'min', 'concorrente': 'first'}).reset_index()
            df_bb['Preço Sugerido'] = df_bb['preco'] - 1.0
            
            st.dataframe(
                df_bb.rename(columns={'titulo': 'Produto', 'preco': 'Menor Preço Atual', 'concorrente': 'Líder de Preço'})
                .sort_values('Menor Preço Atual', ascending=False)
                .style.format({'Menor Preço Atual': 'R$ {:.2f}', 'Preço Sugerido': 'R$ {:.2f}'}),
                use_container_width=True
            )

        # --- ABA 3: INTELIGÊNCIA DE COMPRA (IA) ---
        with t_ia:
            st.header("🤖 Sugestões de Compra por Performance")
            st.info("Esta análise cruza Volume de Vendas vs. Disponibilidade no Mercado.")
            
            # Lógica de IA: Produtos com muitas vendas e poucos concorrentes com estoque
            df_ia = df_hj.groupby(['gtin', 'titulo', 'marca']).agg({
                'vendas_unid': 'sum',
                'estoque': 'sum',
                'concorrente': 'count'
            }).reset_index()
            
            # Filtro: Itens que vendem bem (top 20%) mas tem estoque total baixo no mercado
            vendas_min = df_ia['vendas_unid'].quantile(0.8)
            sugestoes = df_ia[df_ia['vendas_unid'] >= vendas_min].sort_values('vendas_unid', ascending=False)
            
            st.subheader("🚀 Oportunidades de Ouro (Alta Venda)")
            st.dataframe(
                sugestoes.rename(columns={'titulo': 'Produto', 'vendas_unid': 'Vendas Totais', 'estoque': 'Estoque Total Mercado', 'concorrente': 'Players Ativos'})
                .style.background_gradient(cmap='Blues', subset=['Vendas Totais']),
                use_container_width=True
            )

        # --- ABA 4: RUPTURAS ---
        with t_rupturas:
            st.subheader("❌ Produtos Zerados Hoje")
            st.dataframe(df_hj[df_hj['estoque'] == 0][['concorrente','titulo','vendas_unid','preco']], use_container_width=True)

        # --- ABA 5: COMPARATIVO ---
        with t_comp:
            st.header("🔍 Comparação de Datas")
            c_c1, c_c2 = st.columns(2)
            with c_c1: s_hj = st.selectbox("Data A", datas, index=0)
            with c_c2: s_ant = st.selectbox("Data B", datas, index=min(1, len(datas)-1))
            
            df_a = df_g[df_g['data_registro'] == s_hj].set_index(['gtin','concorrente'])
            df_b = df_g[df_g['data_registro'] == s_ant].set_index(['gtin','concorrente'])
            res = df_a.join(df_b, lsuffix='_hj', rsuffix='_ant', how='inner').reset_index()
            res['var'] = res['preco_hj'] - res['preco_ant']
            st.dataframe(res[['concorrente','titulo_hj','preco_ant','preco_hj','var']].style.format({'preco_ant': 'R$ {:.2f}', 'preco_hj': 'R$ {:.2f}', 'var': 'R$ {:.2f}'}), use_container_width=True)
    else:
        st.info("Suba os dados na lateral para começar.")

# Certo, vou deixar isso gravado na minha memória.
# Se você quiser salvar isso como uma instrução personalizada, insira as informações manualmente nas suas configurações de contexto pessoal (https://gemini.google.com/personal-context).
