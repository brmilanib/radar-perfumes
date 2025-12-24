import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime
import time 

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Radar de Perfumes ML", layout="wide", page_icon="💎")

# --- SISTEMA DE LOGIN ---
def check_password():
    """Retorna True se o usuário inseriu a senha correta."""
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if st.session_state["password_correct"]:
        return True

    # Tela de Login com Formulário
    st.markdown("<h1 style='text-align: center;'>💎 Radar PureHome</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.form("login_form"):
            st.subheader("Acesso Restrito")
            user = st.text_input("Usuário")
            pw = st.text_input("Senha", type="password")
            submit = st.form_submit_button("Entrar")

            if submit:
                if (
                    user == st.secrets["credentials"]["usuario"]
                    and pw == st.secrets["credentials"]["senha"]
                ):
                    st.session_state["password_correct"] = True
                    st.rerun() # Recarrega para mostrar o sistema
                else:
                    st.error("😕 Usuário ou senha incorretos.")
        return False
    return False

# Só executa o resto do código se o login for bem-sucedido
if check_password():

    # --- BOTÃO DE LOGOUT NA SIDEBAR ---
    with st.sidebar:
        if st.button("🚪 Sair do Sistema"):
            del st.session_state["password_correct"]
            st.rerun()

    # --- CONEXÃO COM O BANCO (SUPABASE) ---
    @st.cache_resource
    def init_connection():
        try:
            url = st.secrets["SUPABASE_URL"]
            key = st.secrets["SUPABASE_KEY"]
            return create_client(url, key)
        except:
            st.error("❌ Erro nas senhas (Secrets).")
            return None

    supabase = init_connection()

    # --- FUNÇÃO BUSCA PAGINADA (SEM LIMITES) ---
    def busca_dados_completos(datas, lista_concorrentes=None):
        todos_os_dados = []
        offset = 0
        tamanho_pacote = 1000
        bar = st.progress(0, text="Baixando dados do banco...")
        
        while True:
            query = supabase.table('historico_concorrentes').select("*").in_('data_registro', datas)
            if lista_concorrentes:
                query = query.in_('concorrente', lista_concorrentes)
            
            response = query.range(offset, offset + tamanho_pacote - 1).execute()
            dados = response.data
            if not dados: break
            todos_os_dados.extend(dados)
            offset += tamanho_pacote
            bar.progress(min(offset / (offset + 10000), 1.0), text=f"Lendo {offset} linhas...")
            if len(dados) < tamanho_pacote: break
        bar.empty()
        return pd.DataFrame(todos_os_dados)

    st.title("💎 Radar de Inteligência - Mercado Livre")

    # ==============================================================================
    # 1. BARRA LATERAL: UPLOAD E VERSÃO
    # ==============================================================================
    with st.sidebar:
        st.header("📤 Enviar Nova Planilha")
        uploaded_file = st.file_uploader("Arquivo Nubmetrics")
        data_ref = st.date_input("Data destes dados", datetime.now())
        
        nome_padrao = ""
        if uploaded_file:
            try:
                nome_padrao = uploaded_file.name.split('.')[0].replace("PERFUMES_", "").split(" - ")[0]
            except: pass
        
        concorrente_input = st.text_input("Nome do Concorrente", value=nome_padrao)

        if st.button("💾 Salvar no Banco", type="primary"):
            if uploaded_file and concorrente_input and supabase:
                with st.spinner("Processando..."):
                    try:
                        try: df = pd.read_csv(uploaded_file)
                        except: df = pd.read_excel(uploaded_file)
                        
                        dados_envio = []
                        for _, row in df.iterrows():
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
                        
                        chunk_size = 1000
                        for i in range(0, len(dados_envio), chunk_size):
                            supabase.table('historico_concorrentes').insert(dados_envio[i:i+chunk_size]).execute()
                        
                        st.success("✅ Salvo com sucesso!")
                        time.sleep(2) 
                        st.rerun()    
                    except Exception as e:
                        st.error(f"Erro: {e}")

        st.markdown("---")
        st.caption("🛠️ Versão do Sistema: v1.6.2")
        with st.expander("📝 Notas da Atualização"):
            st.markdown("""
            **v1.6.2 (Atual)**
            - ✅ Restauração de cores e R$ nos relatórios.
            - ✅ Adicionada coluna de Estoque nas variações.
            - ✅ Login seguro por formulário.
            """)

    # ==============================================================================
    # 2. ÁREA DE ANÁLISE (ESTILIZADA)
    # ==============================================================================
    if supabase:
        try:
            # Busca as opções de filtro através da View SQL
            df_meta = pd.DataFrame(supabase.table('view_filtros').select("*").execute().data)
            if not df_meta.empty:
                df_meta['data_registro'] = pd.to_datetime(df_meta['data_registro']).dt.date
                lista_datas = sorted(df_meta['data_registro'].unique(), reverse=True)
                lista_concorrentes = sorted(df_meta['concorrente'].unique())
                idx_anterior = 1 if len(lista_datas) > 1 else 0

                st.markdown("### 🔍 Configuração do Relatório")
                c1, c2, c3 = st.columns([2, 1, 1])
                with c1: f_conc = st.multiselect("Filtrar Concorrentes", lista_concorrentes)
                with c2: d_atual = st.selectbox("📅 Data Recente", lista_datas, index=0)
                with c3: d_base = st.selectbox("📅 Comparar com", lista_datas, index=idx_anterior)

                if st.button("🔎 Gerar Análise", type="primary"):
                    df_dados = busca_dados_completos([str(d_base), str(d_atual)], f_conc)
                    
                    if not df_dados.empty:
                        df_dados['data_registro'] = pd.to_datetime(df_dados['data_registro']).dt.date
                        df_hj = df_dados[df_dados['data_registro'] == d_atual].set_index(['gtin', 'concorrente'])
                        df_ant = df_dados[df_dados['data_registro'] == d_base].set_index(['gtin', 'concorrente'])
                        
                        # Cruzamento de dados (Inner Join)
                        df_final = df_hj.join(df_ant, lsuffix='_hj', rsuffix='_ant', how='inner').reset_index()
                        
                        # Cálculos de Performance
                        df_final['diff_preco'] = df_final['preco_hj'] - df_final['preco_ant']
                        df_final['variacao_pct'] = 0.0
                        mask = df_final['preco_ant'] > 0
                        df_final.loc[mask, 'variacao_pct'] = ((df_final['preco_hj'] - df_final['preco_ant']) / df_final['preco_ant']) * 100
                        
                        # Renomeação para exibição
                        df_dis = df_final.rename(columns={
                            'titulo_hj': 'Produto', 
                            'concorrente': 'Concorrente', 
                            'preco_ant': 'Preço ANT', 
                            'preco_hj': 'Preço ATUAL', 
                            'estoque_hj': 'Estoque', 
                            'vendas_unid_hj': 'Vendas'
                        })
                        
                        # KPIs superiores
                        k1, k2, k3 = st.columns(3)
                        k1.metric("Produtos Cruzados", len(df_dis))
                        k2.metric("Subiram 🟢", len(df_dis[df_dis['diff_preco'] > 0.01]))
                        k3.metric("Baixaram 🔴", len(df_dis[df_dis['diff_preco'] < -0.01]))

                        # Abas de navegação
                        t1, t2, t3 = st.tabs(["📈 Variações de Preço", "🏆 Top 50 Vendas", "🚨 Estoque Zerado"])
                        
                        with t1:
                            st.subheader("Quem mudou de preço?")
                            df_v = df_dis[abs(df_dis['diff_preco']) > 0.01].sort_values(by='variacao_pct', ascending=False)
                            if not df_v.empty:
                                st.dataframe(
                                    df_v[['Concorrente', 'Produto', 'Preço ANT', 'Preço ATUAL', 'variacao_pct', 'Estoque']]
                                    .style.format({
                                        'Preço ANT': 'R$ {:.2f}', 
                                        'Preço ATUAL': 'R$ {:.2f}', 
                                        'variacao_pct': '{:+.2f}%'
                                    })
                                    .map(lambda x: 'color: #28a745; font-weight: bold' if x > 0 else 'color: #dc3545; font-weight: bold', subset=['variacao_pct']),
                                    use_container_width=True
                                )
                            else:
                                st.info("Sem variações de preço para estes filtros.")

                        with t2:
                            st.subheader("Produtos que mais vendem")
                            df_t = df_dis.sort_values(by='Vendas', ascending=False).head(50)
                            st.dataframe(
                                df_t[['Vendas', 'Produto', 'Concorrente', 'Preço ATUAL', 'variacao_pct', 'Estoque']]
                                .style.format({
                                    'Preço ATUAL': 'R$ {:.2f}', 
                                    'variacao_pct': '{:+.2f}%'
                                })
                                .map(lambda x: 'color: #28a745' if x > 0 else ('color: #dc3545' if x < 0 else 'color: gray'), subset=['variacao_pct'])
                                .background_gradient(cmap='Greens', subset=['Vendas']),
                                use_container_width=True
                            )

                        with t3:
                            st.subheader("Alerta: Itens que zeraram estoque")
                            z = df_final[(df_final['estoque_hj'] == 0) & (df_final['estoque_ant'] > 0)]
                            if not z.empty:
                                st.dataframe(
                                    z[['concorrente', 'titulo_hj', 'preco_hj', 'estoque_ant']]
                                    .rename(columns={'concorrente': 'Concorrente', 'titulo_hj': 'Produto', 'preco_hj': 'Preço', 'estoque_ant': 'Estoque Anterior'})
                                    .style.format({'Preço': 'R$ {:.2f}'}), 
                                    use_container_width=True
                                )
                            else:
                                st.success("Nenhum produto esgotado detectado no período.")
                                
                    else: st.warning("Não encontrei produtos correspondentes nestas duas datas.")
            else:
                st.info("👋 O banco de dados está vazio. Suba uma planilha na lateral.")
                
        except Exception as e: st.error(f"Erro no processamento dos dados: {e}")
