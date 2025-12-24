import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime
import time
import plotly.express as px

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Radar BI - PureHome", layout="wide", page_icon="📊")

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
        progress_text = "Consultando banco de dados..."
        bar = st.progress(0, text=progress_text)
        
        while True:
            query = supabase.table('historico_concorrentes').select("*")
            if datas: query = query.in_('data_registro', datas)
            if lista_concorrentes: query = query.in_('concorrente', lista_concorrentes)
            
            response = query.range(offset, offset + pacote - 1).execute()
            dados = response.data
            if not dados: break
            todos_os_dados.extend(dados)
            offset += pacote
            bar.progress(min(offset / (offset + 5000), 1.0), text=f"Carregando registros: {len(todos_os_dados)}")
            if len(dados) < pacote: break
        
        bar.empty()
        return pd.DataFrame(todos_os_dados)

    # --- SIDEBAR (UPLOAD) ---
    with st.sidebar:
        st.title("⚙️ Painel de Controle")
        if st.button("🚪 Sair"):
            del st.session_state["password_correct"]
            st.rerun()
        
        st.divider()
        st.subheader("📤 Novo Upload")
        uploaded_file = st.file_uploader("Planilha Nubmetrics", type=["xlsx", "csv"])
        data_ref = st.date_input("Data do arquivo", datetime.now())
        
        nome_sugestao = ""
        if uploaded_file:
            try: nome_sugestao = uploaded_file.name.split('.')[0].replace("PERFUMES_", "").split(" - ")[0]
            except: pass
            
        concorrente_input = st.text_input("Nome do Concorrente", value=nome_sugestao)

        if st.button("💾 Salvar no Banco", type="primary"):
            if uploaded_file and concorrente_input:
                with st.spinner("Enviando dados..."):
                    try:
                        df_up = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('xlsx') else pd.read_csv(uploaded_file)
                        dados_envio = []
                        for _, row in df_up.iterrows():
                            p = pd.to_numeric(row.get('Preço Médio'), errors='coerce')
                            e = pd.to_numeric(row.get('Estoque'), errors='coerce')
                            v = pd.to_numeric(row.get('Vendas em Unid.'), errors='coerce')
                            dados_envio.append({
                                "data_registro": str(data_ref),
                                "concorrente": concorrente_input,
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
                        
                        st.success("✅ Sucesso!")
                        time.sleep(2)
                        st.rerun()
                    except Exception as e: st.error(f"Erro: {e}")

    # ==============================================================================
    # NAVEGAÇÃO PRINCIPAL
    # ==============================================================================
    tab_bi, tab_comp = st.tabs(["📊 DASHBOARD BI", "🔍 COMPARATIVO DIÁRIO"])

    # ------------------------------------------------------------------------------
    # ABA 1: DASHBOARD BI
    # ------------------------------------------------------------------------------
    with tab_bi:
        df_total = busca_dados_completos()
        if not df_total.empty:
            df_total['data_registro'] = pd.to_datetime(df_total['data_registro']).dt.date
            data_recente = df_total['data_registro'].max()
            df_atual = df_total[df_total['data_registro'] == data_recente]

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("SKUs Monitorados", len(df_atual['gtin'].unique()))
            c2.metric("Vendas Totais", f"{df_total['vendas_unid'].sum():,.0f}")
            c3.metric("Ticket Médio", f"R$ {df_atual['preco'].mean():.2f}")
            c4.metric("Rupturas (Estoque 0)", len(df_atual[df_atual['estoque'] == 0]))

            st.divider()
            col_g1, col_g2 = st.columns([2, 1])
            with col_g1:
                st.subheader("📈 Evolução de Vendas")
                vendas_hist = df_total.groupby('data_registro')['vendas_unid'].sum().reset_index()
                fig = px.line(vendas_hist, x='data_registro', y='vendas_unid', markers=True, template="plotly_white")
                st.plotly_chart(fig, use_container_width=True)
            with col_g2:
                st.subheader("🏆 Market Share (Marcas)")
                marcas_df = df_atual.groupby('marca')['vendas_unid'].sum().sort_values(ascending=False).head(10)
                st.bar_chart(marcas_df)
        else:
            st.info("Aguardando dados para gerar inteligência...")

    # ------------------------------------------------------------------------------
    # ABA 2: COMPARATIVO DIÁRIO (RESTAURADA)
    # ------------------------------------------------------------------------------
    with tab_comp:
        try:
            df_meta = pd.DataFrame(supabase.table('view_filtros').select("*").execute().data)
            if not df_meta.empty:
                df_meta['data_registro'] = pd.to_datetime(df_meta['data_registro']).dt.date
                lista_datas = sorted(df_meta['data_registro'].unique(), reverse=True)
                lista_concs = sorted(df_meta['concorrente'].unique())

                st.markdown("### 🔍 Configurar Comparação")
                c1, c2, c3 = st.columns([2, 1, 1])
                with c1: f_concs = st.multiselect("Concorrentes", lista_concs)
                with c2: d_hj = st.selectbox("Data Atual", lista_datas, index=0)
                with c3: d_ant = st.selectbox("Data Anterior", lista_datas, index=min(1, len(lista_datas)-1))

                if st.button("🔎 Analisar Variações", type="primary"):
                    df_comp = busca_dados_completos([str(d_hj), str(d_ant)], f_concs)
                    if not df_comp.empty:
                        df_comp['data_registro'] = pd.to_datetime(df_comp['data_registro']).dt.date
                        df_h = df_comp[df_comp['data_registro'] == d_hj].set_index(['gtin', 'concorrente'])
                        df_a = df_comp[df_comp['data_registro'] == d_ant].set_index(['gtin', 'concorrente'])
                        
                        df_f = df_h.join(df_a, lsuffix='_hj', rsuffix='_ant', how='inner').reset_index()
                        df_f['diff_preco'] = df_f['preco_hj'] - df_f['preco_ant']
                        df_f['var_pct'] = 0.0
                        df_f.loc[df_f['preco_ant'] > 0, 'var_pct'] = ((df_f['preco_hj'] - df_f['preco_ant']) / df_f['preco_ant']) * 100
                        
                        df_res = df_f.rename(columns={'titulo_hj': 'Produto', 'concorrente': 'Concorrente', 'preco_ant': 'Preço ANT', 'preco_hj': 'Preço ATUAL', 'estoque_hj': 'Estoque', 'vendas_unid_hj': 'Vendas'})
                        
                        st.divider()
                        sub_tab1, sub_tab2, sub_tab3 = st.tabs(["📈 Variações", "🏆 Top 50", "🚨 Estoque Zero"])
                        
                        with sub_tab1:
                            df_v = df_res[abs(df_res['diff_preco']) > 0.01].sort_values(by='var_pct', ascending=False)
                            st.dataframe(df_v[['Concorrente', 'Produto', 'Preço ANT', 'Preço ATUAL', 'var_pct', 'Estoque']].style.format({'Preço ANT': 'R$ {:.2f}', 'Preço ATUAL': 'R$ {:.2f}', 'var_pct': '{:+.2f}%'}).map(lambda x: 'color: #28a745' if x > 0 else 'color: #dc3545', subset=['var_pct']), use_container_width=True)
                        
                        with sub_tab2:
                            df_t = df_res.sort_values(by='Vendas', ascending=False).head(50)
                            st.dataframe(df_t[['Vendas', 'Produto', 'Concorrente', 'Preço ATUAL', 'var_pct', 'Estoque']].style.format({'Preço ATUAL': 'R$ {:.2f}', 'var_pct': '{:+.2f}%'}).background_gradient(cmap='Greens', subset=['Vendas']), use_container_width=True)
                        
                        with sub_tab3:
                            z = df_f[(df_f['estoque_hj'] == 0) & (df_f['estoque_ant'] > 0)]
                            st.dataframe(z[['concorrente', 'titulo_hj', 'preco_hj', 'estoque_ant']].rename(columns={'concorrente': 'Concorrente', 'titulo_hj': 'Produto', 'preco_hj': 'Preço', 'estoque_ant': 'Estoque ANT'}).style.format({'Preço': 'R$ {:.2f}'}), use_container_width=True)
                    else: st.warning("Dados insuficientes para cruzar.")
        except Exception as e: st.error(f"Erro no comparativo: {e}")
