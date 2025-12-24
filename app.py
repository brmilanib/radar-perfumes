import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime
import time
import plotly.express as px
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Radar BI Pro - PureHome", layout="wide", page_icon="📈")

# --- FUNÇÃO PARA LIMPAR NOMES DE CONCORRENTES ---
def normalizar_concorrente(nome):
    """Remove (1), (2), espaços extras e números para unificar o concorrente."""
    nome = re.sub(r'\s*\(\d+\)\s*', '', str(nome)) # Remove (1), (2), etc
    return nome.strip().upper()

# --- SISTEMA DE LOGIN ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]:
        return True

    st.markdown("<h1 style='text-align: center;'>💎 Radar PureHome</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.subheader("Acesso Restrito")
            user = st.text_input("Usuário")
            pw = st.text_input("Senha", type="password")
            submit = st.form_submit_button("Entrar")
            if submit:
                if user == st.secrets["credentials"]["usuario"] and pw == st.secrets["credentials"]["senha"]:
                    st.session_state["password_correct"] = True
                    st.rerun()
                else:
                    st.error("😕 Usuário ou senha incorretos.")
        return False
    return False

if check_password():
    # --- CONEXÃO ---
    @st.cache_resource
    def init_connection():
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

    supabase = init_connection()

    # --- FUNÇÃO BUSCA PAGINADA ---
    def busca_dados_completos(datas=None, lista_concorrentes=None):
        todos_os_dados = []
        offset = 0
        pacote = 1000
        while True:
            query = supabase.table('historico_concorrentes').select("*")
            if datas: query = query.in_('data_registro', datas)
            if lista_concorrentes: query = query.in_('concorrente', lista_concorrentes)
            response = query.range(offset, offset + pacote - 1).execute()
            dados = response.data
            if not dados: break
            todos_os_dados.extend(dados)
            offset += pacote
            if len(dados) < pacote: break
        df = pd.DataFrame(todos_os_dados)
        if not df.empty:
            df['concorrente'] = df['concorrente'].apply(normalizar_concorrente)
        return df

    # --- SIDEBAR ---
    with st.sidebar:
        st.title("⚙️ Painel Admin")
        if st.button("🚪 Sair"):
            del st.session_state["password_correct"]
            st.rerun()
        st.divider()
        st.subheader("📤 Upload Planilha")
        uploaded_file = st.file_uploader("Arquivo Nubmetrics", type=["xlsx", "csv"])
        data_ref = st.date_input("Data do Registro", datetime.now())
        c_input = st.text_input("Nome do Concorrente (Será normalizado)")
        
        if st.button("💾 Salvar Dados", type="primary"):
            if uploaded_file and c_input:
                with st.spinner("Enviando..."):
                    df_up = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('xlsx') else pd.read_csv(uploaded_file)
                    dados_envio = []
                    conc_limpo = normalizar_concorrente(c_input)
                    for _, row in df_up.iterrows():
                        p = pd.to_numeric(row.get('Preço Médio'), errors='coerce')
                        e = pd.to_numeric(row.get('Estoque'), errors='coerce')
                        v = pd.to_numeric(row.get('Vendas em Unid.'), errors='coerce')
                        dados_envio.append({
                            "data_registro": str(data_ref),
                            "concorrente": conc_limpo,
                            "titulo": str(row.get('Título', ''))[:200],
                            "gtin": str(row.get('GTIN', '')).replace('.0', '').strip(),
                            "marca": str(row.get('Marca', '')),
                            "preco": float(p) if pd.notnull(p) else 0.0,
                            "estoque": int(e) if pd.notnull(e) else 0,
                            "vendas_unid": int(v) if pd.notnull(v) else 0,
                            "sku_concorrente": str(row.get('SKU', ''))
                        })
                    for i in range(0, len(dados_envio), 1000):
                        supabase.table('historico_concorrentes').insert(dados_envio[i:i+1000]).execute()
                    st.success("✅ Salvo e Normalizado!")
                    time.sleep(2); st.rerun()

    # ==============================================================================
    # NAVEGAÇÃO PRINCIPAL (ABAS DE MONITORAMENTO)
    # ==============================================================================
    tab_dashboard, tab_skus, tab_rupturas, tab_comparativo = st.tabs([
        "📊 Dashboard Geral", "📋 SKUs Monitorados", "🚨 Rupturas & Reposição", "🔍 Comparativo Diário"
    ])

    # Carregamento Global para o Dashboard
    df_global = busca_dados_completos()
    
    if not df_global.empty:
        df_global['data_registro'] = pd.to_datetime(df_global['data_registro']).dt.date
        datas_lista = sorted(df_global['data_registro'].unique(), reverse=True)
        data_hj = datas_lista[0]
        data_ant = datas_lista[1] if len(datas_lista) > 1 else data_hj
        
        df_hj_full = df_global[df_global['data_registro'] == data_hj]

        # ------------------------------------------------------------------------------
        # ABA 1: DASHBOARD GERAL
        # ------------------------------------------------------------------------------
        with tab_dashboard:
            st.header(f"Resumo de Mercado - {data_hj.strftime('%d/%m/%Y')}")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("SKUs Totais", len(df_hj_full))
            
            faturamento_total = (df_hj_full['vendas_unid'] * df_hj_full['preco']).sum()
            c2.metric("Faturamento Estimado", f"R$ {faturamento_total:,.2f}")
            c3.metric("Ticket Médio", f"R$ {df_hj_full['preco'].mean():.2f}")
            
            rupturas_count = len(df_hj_full[df_hj_full['estoque'] == 0])
            c4.metric("Itens s/ Estoque", rupturas_count)

            st.divider()
            col_a, col_b = st.columns([1, 1])
            
            with col_a:
                st.subheader("Faturamento por Marca (Top 10)")
                df_hj_full['faturamento'] = df_hj_full['vendas_unid'] * df_hj_full['preco']
                marcas = df_hj_full.groupby('marca')['faturamento'].sum().sort_values(ascending=False).head(10).reset_index()
                fig_m = px.bar(marcas, x='marca', y='faturamento', text_auto='.3s', color='faturamento', color_continuous_scale='Greens')
                fig_m.update_traces(texttemplate='R$ %{y:.2s}', textposition='outside')
                st.plotly_chart(fig_m, use_container_width=True)

            with col_b:
                st.subheader("Performance por Concorrente (Faturamento Diário)")
                df_global['fat_total'] = df_global['vendas_unid'] * df_global['preco']
                conc_evol = df_global.groupby(['data_registro', 'concorrente'])['fat_total'].sum().reset_index()
                fig_c = px.line(conc_evol, x='data_registro', y='fat_total', color='concorrente', markers=True)
                st.plotly_chart(fig_c, use_container_width=True)

        # ------------------------------------------------------------------------------
        # ABA 2: SKUs MONITORADOS (COM BUSCA)
        # ------------------------------------------------------------------------------
        with tab_skus:
            st.header("📋 Todos os Produtos Monitorados")
            search = st.text_input("🔍 Buscar por Produto, Marca ou GTIN")
            
            df_s = df_hj_full.sort_values(by='vendas_unid', ascending=False).copy()
            if search:
                df_s = df_s[df_s['titulo'].str.contains(search, case=False) | df_s['gtin'].str.contains(search) | df_s['marca'].str.contains(search, case=False)]
            
            st.dataframe(
                df_s[['vendas_unid', 'titulo', 'concorrente', 'gtin', 'preco', 'estoque', 'marca']]
                .rename(columns={'vendas_unid': 'Vendas', 'titulo': 'Produto', 'preco': 'Preço'})
                .style.format({'Preço': 'R$ {:.2f}'})
                .background_gradient(cmap='Greens', subset=['Vendas']),
                use_container_width=True, height=700
            )

        # ------------------------------------------------------------------------------
        # ABA 3: RUPTURAS & REPOSIÇÃO
        # ------------------------------------------------------------------------------
        with tab_rupturas:
            st.header("🚨 Controle de Estoque")
            
            # Reposição: Estava 0 antes e agora tem > 0
            df_ant_full = df_global[df_global['data_registro'] == data_ant]
            df_rep = df_hj_full[df_hj_full['estoque'] > 0].set_index(['gtin', 'concorrente'])
            df_ant_zero = df_ant_full[df_ant_full['estoque'] == 0].set_index(['gtin', 'concorrente'])
            df_reposicao = df_rep.join(df_ant_zero, lsuffix='_hj', rsuffix='_ant', how='inner').reset_index()

            col_r1, col_r2 = st.columns(2)
            with col_r1:
                st.subheader("❌ Atualmente Zerados")
                df_z = df_hj_full[df_hj_full['estoque'] == 0].sort_values(by='vendas_unid', ascending=False)
                st.dataframe(df_z[['concorrente', 'titulo', 'vendas_unid', 'preco']].rename(columns={'vendas_unid': 'Vendas Hist.', 'preco': 'Preço'}), use_container_width=True)

            with col_r2:
                st.subheader("✅ Itens Repostos (Voltaram ao estoque)")
                st.dataframe(df_reposicao[['concorrente', 'titulo_hj', 'estoque_hj', 'preco_hj']].rename(columns={'titulo_hj': 'Produto', 'estoque_hj': 'Novo Estoque', 'preco_hj': 'Preço'}), use_container_width=True)

        # ------------------------------------------------------------------------------
        # ABA 4: COMPARATIVO DIÁRIO (RESTAURADA TOTAL)
        # ------------------------------------------------------------------------------
        with tab_comparativo:
            st.header("🔍 Comparativo de Variação")
            c_comp1, c_comp2, c_comp3 = st.columns([2, 1, 1])
            with c_comp1: 
                lista_c = sorted(df_global['concorrente'].unique())
                sel_c = st.multiselect("Filtrar Concorrentes", lista_c)
            with c_comp2: sel_hj = st.selectbox("Data Atual", datas_lista, index=0)
            with c_comp3: sel_ant = st.selectbox("Data Base", datas_lista, index=min(1, len(datas_lista)-1))

            if st.button("Executar Comparação Diária"):
                df_c_hj = df_global[(df_global['data_registro'] == sel_hj)].set_index(['gtin', 'concorrente'])
                df_c_ant = df_global[(df_global['data_registro'] == sel_ant)].set_index(['gtin', 'concorrente'])
                
                if sel_c:
                    df_c_hj = df_c_hj[df_c_hj.index.get_level_values('concorrente').isin(sel_c)]
                    df_c_ant = df_c_ant[df_c_ant.index.get_level_values('concorrente').isin(sel_c)]

                df_res = df_c_hj.join(df_c_ant, lsuffix='_hj', rsuffix='_ant', how='inner').reset_index()
                df_res['var_pre'] = df_res['preco_hj'] - df_res['preco_ant']
                df_res['var_pct'] = ((df_res['preco_hj'] - df_res['preco_ant']) / df_res['preco_ant']) * 100
                
                st.dataframe(
                    df_res[['concorrente', 'titulo_hj', 'preco_ant', 'preco_hj', 'var_pct', 'estoque_hj', 'vendas_unid_hj']]
                    .rename(columns={'titulo_hj': 'Produto', 'preco_ant': 'Preço Ant.', 'preco_hj': 'Preço Hoje', 'var_pct': '% Var', 'estoque_hj': 'Estoque', 'vendas_unid_hj': 'Vendas'})
                    .style.format({'Preço Ant.': 'R$ {:.2f}', 'Preço Hoje': 'R$ {:.2f}', '% Var': '{:+.2f}%'})
                    .map(lambda x: 'color: green; font-weight: bold' if x > 0 else ('color: red; font-weight: bold' if x < 0 else 'color: gray'), subset=['% Var']),
                    use_container_width=True
                )
    else:
        st.info("Aguardando o primeiro upload de dados.")
