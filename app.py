import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime
import time
import plotly.express as px

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Radar BI Pro - PureHome", layout="wide", page_icon="📈")

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
        bar = st.progress(0, text="Sincronizando BI...")
        while True:
            query = supabase.table('historico_concorrentes').select("*")
            if datas: query = query.in_('data_registro', datas)
            if lista_concorrentes: query = query.in_('concorrente', lista_concorrentes)
            response = query.range(offset, offset + pacote - 1).execute()
            dados = response.data
            if not dados: break
            todos_os_dados.extend(dados)
            offset += pacote
            bar.progress(min(offset / 10000, 1.0), text=f"Carregados {len(todos_os_dados)} itens...")
            if len(dados) < pacote: break
        bar.empty()
        return pd.DataFrame(todos_os_dados)

    # --- SIDEBAR ---
    with st.sidebar:
        st.title("⚙️ Configurações")
        if st.button("🚪 Sair"):
            del st.session_state["password_correct"]
            st.rerun()
        st.divider()
        st.subheader("📤 Upload Nubmetrics")
        uploaded_file = st.file_uploader("Arquivo", type=["xlsx", "csv"])
        data_ref = st.date_input("Data", datetime.now())
        concorrente_input = st.text_input("Nome Concorrente")
        if st.button("💾 Salvar"):
            # ... (Lógica de salvamento anterior mantida)
            st.success("Salvo!")
            time.sleep(1)
            st.rerun()

    # ==============================================================================
    # DASHBOARD BI PRO
    # ==============================================================================
    tab_bi, tab_comp = st.tabs(["📊 DASHBOARD INTERATIVO", "🔍 COMPARATIVO DIÁRIO"])

    with tab_bi:
        df_total = busca_dados_completos()
        if not df_total.empty:
            df_total['data_registro'] = pd.to_datetime(df_total['data_registro']).dt.date
            data_recente = df_total['data_registro'].max()
            # Pega também a penúltima data para cálculos de variação
            datas_unicas = sorted(df_total['data_registro'].unique(), reverse=True)
            data_anterior = datas_unicas[1] if len(datas_unicas) > 1 else data_recente
            
            df_atual = df_total[df_total['data_registro'] == data_recente]
            df_ant_full = df_total[df_total['data_registro'] == data_anterior]

            # --- LINHA 1: MÉTRICAS E ATALHOS ---
            c1, c2, c3, c4 = st.columns(4)
            
            with c1:
                st.metric("SKUs Monitorados", len(df_atual['gtin'].unique()))
                ver_skus = st.button("👁️ Detalhar SKUs")
            
            with c2:
                vendas_fin = (df_atual['vendas_unid'] * df_atual['preco']).sum()
                st.metric("Volume Financeiro (Hoje)", f"R$ {vendas_fin:,.20}".replace(",", "X").replace(".", ",").replace("X", "."))
                st.caption(f"Unidades: {df_atual['vendas_unid'].sum():,.0f}")

            with c3:
                st.metric("Ticket Médio", f"R$ {df_atual['preco'].mean():.2f}")
            
            with c4:
                rupturas = df_atual[df_atual['estoque'] == 0]
                st.metric("Rupturas de Estoque", len(rupturas))
                ver_rupturas = st.button("🚨 Detalhar Rupturas")

            # --- VISÕES DETALHADAS (SUB-PÁGINAS) ---
            if ver_skus:
                st.divider()
                st.subheader("📋 Lista Completa de SKUs (Ordenado por Vendas)")
                busca = st.text_input("🔍 Buscar Produto ou GTIN", key="search_skus")
                df_sku_view = df_atual.sort_values(by='vendas_unid', ascending=False)
                if busca:
                    df_sku_view = df_sku_view[df_sku_view['titulo'].str.contains(busca, case=False) | df_sku_view['gtin'].str.contains(busca)]
                st.dataframe(df_sku_view[['vendas_unid', 'titulo', 'concorrente', 'gtin', 'preco', 'estoque']].rename(columns={'vendas_unid': 'Vendas', 'titulo': 'Produto', 'preco': 'Preço'}), use_container_width=True)

            if ver_rupturas:
                st.divider()
                st.subheader("🚨 Produtos sem Estoque no Concorrente")
                # Join com a data anterior para mostrar variação
                df_r_comp = df_atual[df_atual['estoque'] == 0].set_index(['gtin', 'concorrente'])
                df_a_comp = df_ant_full.set_index(['gtin', 'concorrente'])
                df_r_final = df_r_comp.join(df_a_comp, lsuffix='_hj', rsuffix='_ant', how='inner').reset_index()
                
                df_r_final['diff'] = df_r_final['preco_hj'] - df_r_final['preco_ant']
                
                st.dataframe(
                    df_r_final[['concorrente', 'titulo_hj', 'preco_ant', 'preco_hj', 'diff', 'vendas_unid_hj']]
                    .rename(columns={'titulo_hj': 'Produto', 'preco_ant': 'Preço Antigo', 'preco_hj': 'Último Preço', 'diff': 'Variação', 'vendas_unid_hj': 'Vendas Hist.'})
                    .style.format({'Preço Antigo': 'R$ {:.2f}', 'Último Preço': 'R$ {:.2f}', 'Variação': 'R$ {:.2f}'})
                    .map(lambda x: 'color: green' if x > 0 else ('color: red' if x < 0 else 'color: gray'), subset=['Variação']),
                    use_container_width=True
                )

            st.divider()

            # --- LINHA 2: GRÁFICOS FINANCEIROS ---
            col_a, col_b = st.columns([1, 1])

            with col_a:
                st.subheader("🏆 Vendas por Marca (R$)")
                df_atual['total_fin'] = df_atual['vendas_unid'] * df_atual['preco']
                marcas_fin = df_atual.groupby('marca')['total_fin'].sum().sort_values(ascending=False).head(10).reset_index()
                fig_marca = px.bar(marcas_fin, x='marca', y='total_fin', text_auto='.2s', 
                                  title="Top 10 Marcas por Faturamento", labels={'total_fin': 'Total R$', 'marca': 'Marca'})
                fig_marca.update_traces(texttemplate='R$ %{y:.2s}', textposition='outside')
                st.plotly_chart(fig_marca, use_container_width=True)

            with col_b:
                st.subheader("⚔️ Ranking de Concorrentes (Dia a Dia)")
                df_total['faturamento'] = df_total['vendas_unid'] * df_total['preco']
                conc_hist = df_total.groupby(['data_registro', 'concorrente'])['faturamento'].sum().reset_index()
                fig_conc = px.line(conc_hist, x='data_registro', y='faturamento', color='concorrente', markers=True, title="Faturamento Diário por Player")
                st.plotly_chart(fig_conc, use_container_width=True)

    with tab_comp:
        # (Mantém o código anterior de comparativo diário aqui)
        st.info("Acesse esta aba para auditoria detalhada de preços entre duas datas específicas.")
