import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime
import time 

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Radar de Perfumes ML", layout="wide", page_icon="💎")

# --- CONEXÃO COM O BANCO (SUPABASE) ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except:
        st.error("❌ Erro nas senhas (Secrets). Verifique se configurou SUPABASE_URL e SUPABASE_KEY no Streamlit Cloud.")
        return None

supabase = init_connection()

# --- FUNÇÃO NOVA: BUSCA PAGINADA (SEM LIMITES) ---
def busca_dados_completos(datas, lista_concorrentes=None):
    """
    Busca dados no Supabase de 1000 em 1000 para contornar o limite da API.
    Garante que TODOS os produtos sejam lidos.
    """
    todos_os_dados = []
    offset = 0
    tamanho_pacote = 1000
    
    # Barra de progresso para o usuário não achar que travou
    bar = st.progress(0, text="Baixando dados do banco...")
    
    while True:
        # Monta a query
        query = supabase.table('historico_concorrentes').select("*").in_('data_registro', datas)
        
        if lista_concorrentes:
            query = query.in_('concorrente', lista_concorrentes)
            
        # Pega o pacote atual (Ex: do 0 ao 1000, depois do 1000 ao 2000...)
        response = query.range(offset, offset + tamanho_pacote - 1).execute()
        dados = response.data
        
        if not dados:
            break # Acabaram os dados
            
        todos_os_dados.extend(dados)
        
        # Atualiza barra
        offset += tamanho_pacote
        bar.progress(min(offset / (offset + 5000), 1.0), text=f"Lendo linhas {offset}...")
        
        # Se veio menos que o pacote, é porque acabou
        if len(dados) < tamanho_pacote:
            break
            
    bar.empty() # Remove a barra
    return pd.DataFrame(todos_os_dados)

# --- ESTILO CSS ---
st.markdown("""
<style>
    .metric-card {background-color: #f0f2f6; border-radius: 10px; padding: 15px; border: 1px solid #e0e0e0;}
    [data-testid="stMetricValue"] {font-size: 24px; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

st.title("💎 Radar de Inteligência - Mercado Livre")

# ==============================================================================
# 1. BARRA LATERAL: UPLOAD E FILTROS
# ==============================================================================
with st.sidebar:
    st.header("📤 Enviar Nova Planilha")
    uploaded_file = st.file_uploader("Arquivo Nubmetrics (.csv ou .xlsx)")
    
    data_ref = st.date_input("Data destes dados", datetime.now())
    
    nome_padrao = ""
    if uploaded_file:
        try:
            nome_sugerido = uploaded_file.name.split('.')[0].replace("PERFUMES_", "").split(" - ")[0]
            nome_padrao = nome_sugerido
        except:
            nome_padrao = ""
    
    concorrente_input = st.text_input("Nome do Concorrente", value=nome_padrao)

    # BOTÃO DE UPLOAD
    if st.button("💾 Salvar no Banco de Dados", type="primary"):
        if uploaded_file and concorrente_input and supabase:
            with st.spinner("Processando e enviando para a nuvem..."):
                try:
                    try:
                        df = pd.read_csv(uploaded_file)
                    except:
                        df = pd.read_excel(uploaded_file)
                    
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
                        
                    st.success(f"✅ Sucesso! {len(dados_envio)} produtos salvos! Atualizando...")
                    time.sleep(2) 
                    st.rerun()    
                    
                except Exception as e:
                    st.error(f"Erro ao processar arquivo: {e}")
        else:
            st.warning("Preencha o arquivo e o nome do concorrente.")

    # --- CHANGELOG ---
    st.markdown("---")
    st.caption("🛠️ Versão do Sistema: v1.5")
    with st.expander("📝 Notas da Atualização"):
        st.markdown("""
        **v1.5 (Atual)**
        - 🚀 CORREÇÃO CRÍTICA: Sistema agora lê bases gigantes (>1000 produtos) sem cortar dados.
        - Adicionada barra de progresso no carregamento.
        
        **v1.4**
        - Otimização de Filtros (View).
        """)

# ==============================================================================
# 2. ÁREA DE ANÁLISE (RELATÓRIOS)
# ==============================================================================

if supabase:
    try:
        # Usa a View Leve para os filtros
        df_meta = pd.DataFrame(supabase.table('view_filtros').select("*").execute().data)
        
        if not df_meta.empty:
            df_meta['data_registro'] = pd.to_datetime(df_meta['data_registro']).dt.date
            
            lista_datas = sorted(df_meta['data_registro'].unique(), reverse=True)
            lista_concorrentes = sorted(df_meta['concorrente'].unique())
            
            idx_anterior = 1 if len(lista_datas) > 1 else 0

            st.markdown("### 🔍 Configuração do Relatório")
            c1, c2, c3 = st.columns([2, 1, 1])
            
            with c1:
                filtro_concorrentes = st.multiselect("Filtrar Concorrentes", lista_concorrentes, placeholder="Todos os Concorrentes")
            with c2:
                data_atual = st.selectbox("📅 Data Recente (Hoje)", lista_datas, index=0)
            with c3:
                data_base = st.selectbox("📅 Comparar com (Anterior)", lista_datas, index=idx_anterior)

            if st.button("🔎 Gerar Análise de Mercado", type="primary"):
                
                # --- AQUI ESTÁ A MUDANÇA: Usamos a função nova ---
                df_dados = busca_dados_completos(
                    datas=[str(data_base), str(data_atual)], 
                    lista_concorrentes=filtro_concorrentes
                )

                if not df_dados.empty:
                    df_dados['data_registro'] = pd.to_datetime(df_dados['data_registro']).dt.date
                    
                    df_hoje = df_dados[df_dados['data_registro'] == data_atual].set_index(['gtin', 'concorrente'])
                    df_antes = df_dados[df_dados['data_registro'] == data_base].set_index(['gtin', 'concorrente'])
                    
                    # Inner Join (Só compara o que existe nos DOIS dias)
                    df_final = df_hoje.join(df_antes, lsuffix='_hj', rsuffix='_ant', how='inner').reset_index()
                    
                    # Cálculos
                    df_final['diff_preco'] = df_final['preco_hj'] - df_final['preco_ant']
                    # Evita divisão por zero
                    df_final['variacao_pct'] = 0.0
                    mask_valid = df_final['preco_ant'] > 0
                    df_final.loc[mask_valid, 'variacao_pct'] = ((df_final.loc[mask_valid, 'preco_hj'] - df_final.loc[mask_valid, 'preco_ant']) / df_final.loc[mask_valid, 'preco_ant']) * 100
                    
                    # Renomear
                    df_display = df_final.rename(columns={
                        'titulo_hj': 'Produto',
                        'concorrente': 'Concorrente',
                        'preco_ant': 'Preço ANTES',
                        'preco_hj': 'Preço AGORA',
                        'estoque_hj': 'Estoque Atual',
                        'vendas_unid_hj': 'Vendas (Unid)',
                        'marca_hj': 'Marca'
                    })

                    # KPIs
                    total_prods = len(df_display)
                    # Consideramos alteração qualquer coisa maior que 1 centavo para ignorar arredondamentos
                    subiu = len(df_display[df_display['diff_preco'] > 0.01])
                    caiu = len(df_display[df_display['diff_preco'] < -0.01])
                    
                    k1, k2, k3 = st.columns(3)
                    k1.metric("Produtos Cruzados (Iguais nos 2 dias)", total_prods)
                    k2.metric("Subiram Preço 🟢", subiu, delta="Oportunidade")
                    k3.metric("Baixaram Preço 🔴", caiu, delta="- Cuidado", delta_color="inverse")
                    
                    st.divider()

                    # ABAS
                    tab1, tab2, tab3 = st.tabs(["📈 Variação de Preço", "🏆 Top 50 Mais Vendidos", "🚨 Estoque Zerado"])

                    # ABA 1
                    with tab1:
                        st.subheader("Quem mudou de preço?")
                        df_var = df_display[abs(df_display['diff_preco']) > 0.01].copy()
                        
                        if not df_var.empty:
                            df_var = df_var.sort_values(by='variacao_pct', ascending=False)
                            st.dataframe(
                                df_var[['Concorrente', 'Produto', 'Preço ANTES', 'Preço AGORA', 'variacao_pct', 'Estoque Atual']].style
                                .format({
                                    'Preço ANTES': 'R$ {:.2f}',
                                    'Preço AGORA': 'R$ {:.2f}',
                                    'variacao_pct': '{:+.2f}%',
                                    'Estoque Atual': '{:.0f}'
                                })
                                .map(lambda x: 'color: green; font-weight: bold' if x > 0 else 'color: red; font-weight: bold', subset=['variacao_pct']),
                                use_container_width=True, height=600
                            )
                        else:
                            st.info("Nenhuma alteração de preço detectada nos produtos cruzados.")

                    # ABA 2
                    with tab2:
                        st.subheader(f"🏆 Top 50 Mais Vendidos")
                        # Garante que Vendas seja numérico
                        df_display['Vendas (Unid)'] = pd.to_numeric(df_display['Vendas (Unid)'], errors='coerce').fillna(0)
                        df_top = df_display.sort_values(by='Vendas (Unid)', ascending=False).head(50)
                        
                        cols_top = ['Produto', 'Concorrente', 'Vendas (Unid)', 'Preço ANTES', 'Preço AGORA', 'variacao_pct', 'Estoque Atual']
                        
                        st.dataframe(
                            df_top[cols_top].style
                            .format({
                                'Preço ANTES': 'R$ {:.2f}',
                                'Preço AGORA': 'R$ {:.2f}',
                                'variacao_pct': '{:+.2f}%',
                                'Vendas (Unid)': '{:.0f}',
                                'Estoque Atual': '{:.0f}'
                            })
                            .map(lambda x: 'color: green; font-weight: bold' if x > 0 else ('color: red; font-weight: bold' if x < 0 else 'color: gray'), subset=['variacao_pct'])
                            .background_gradient(subset=['Vendas (Unid)'], cmap='Greens'),
                            use_container_width=True
                        )

                    # ABA 3 - ESTOQUE ZERADO
                    # Atenção: Estoque Zerado precisa pegar quem tinha estoque ANTES e agora é 0.
                    with tab3:
                        st.subheader("🚨 Produtos que ZERARAM no Concorrente")
                        zerados = df_final[(df_final['estoque_hj'] == 0) & (df_final['estoque_ant'] > 0)].copy()
                        
                        if not zerados.empty:
                            st.dataframe(
                                zerados[['concorrente', 'titulo_hj', 'preco_hj', 'estoque_ant']].rename(columns={
                                    'concorrente': 'Concorrente',
                                    'titulo_hj': 'Produto',
                                    'preco_hj': 'Preço (Último)',
                                    'estoque_ant': 'Estoque ANTES'
                                }).style.format({
                                    'Preço (Último)': 'R$ {:.2f}',
                                    'Estoque ANTES': '{:.0f}'
                                }),
                                use_container_width=True
                            )
                        else:
                            st.success("Nenhum concorrente zerou estoque de produtos que já existiam na data anterior.")

                else:
                    st.warning("Não encontrei dados suficientes para cruzar essas duas datas.")

        else:
            st.info("👋 Bem-vindo! Suba sua primeira planilha.")

    except Exception as e:
        st.error(f"Erro ao carregar sistema: {e}")
else:
    st.stop()
