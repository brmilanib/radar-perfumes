import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime

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

# --- ESTILO CSS PERSONALIZADO (Para ficar bonito) ---
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
    
    # Data do arquivo (Default: Hoje)
    data_ref = st.date_input("Data destes dados", datetime.now())
    
    # Tenta adivinhar o nome do concorrente pelo nome do arquivo
    nome_padrao = ""
    if uploaded_file:
        nome_sugerido = uploaded_file.name.split('.')[0].replace("PERFUMES_", "").split(" - ")[0]
        nome_padrao = nome_sugerido
    
    concorrente_input = st.text_input("Nome do Concorrente", value=nome_padrao)

    # BOTÃO DE UPLOAD
    if st.button("💾 Salvar no Banco de Dados", type="primary"):
        if uploaded_file and concorrente_input and supabase:
            with st.spinner("Processando e enviando para a nuvem..."):
                try:
                    # Lê Excel ou CSV
                    try:
                        df = pd.read_csv(uploaded_file)
                    except:
                        df = pd.read_excel(uploaded_file)
                    
                    # Prepara os dados (Limpeza)
                    dados_envio = []
                    for _, row in df.iterrows():
                        # Converte valores monetários e numéricos com segurança
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
                    
                    # Envia em pacotes de 1000 para não travar
                    chunk_size = 1000
                    for i in range(0, len(dados_envio), chunk_size):
                        supabase.table('historico_concorrentes').insert(dados_envio[i:i+chunk_size]).execute()
                        
                    st.success(f"✅ Sucesso! {len(dados_envio)} produtos registrados para o dia {data_ref}.")
                    st.balloons()
                    
                except Exception as e:
                    st.error(f"Erro ao processar arquivo: {e}")
        else:
            st.warning("Preencha o arquivo e o nome do concorrente.")

    st.markdown("---")
    st.info("💡 Dica: Suba os dados diariamente para ter histórico de preços.")

# ==============================================================================
# 2. ÁREA DE ANÁLISE (RELATÓRIOS)
# ==============================================================================

if supabase:
    try:
        # Busca metadados para montar os filtros
        df_meta = pd.DataFrame(supabase.table('historico_concorrentes').select("concorrente, data_registro").execute().data)
        
        if not df_meta.empty:
            df_meta['data_registro'] = pd.to_datetime(df_meta['data_registro']).dt.date
            
            # Ordena datas (Mais recente primeiro)
            lista_datas = sorted(df_meta['data_registro'].unique(), reverse=True)
            lista_concorrentes = sorted(df_meta['concorrente'].unique())
            
            # Define datas padrão (Hoje vs Ontem)
            idx_anterior = 1 if len(lista_datas) > 1 else 0

            # --- FILTROS NO TOPO ---
            st.markdown("### 🔍 Configuração do Relatório")
            c1, c2, c3 = st.columns([2, 1, 1])
            
            with c1:
                filtro_concorrentes = st.multiselect("Filtrar Concorrentes", lista_concorrentes, placeholder="Todos os Concorrentes")
            with c2:
                data_atual = st.selectbox("📅 Data Recente (Hoje)", lista_datas, index=0)
            with c3:
                data_base = st.selectbox("📅 Comparar com (Anterior)", lista_datas, index=idx_anterior)

            # --- BOTÃO DE GERAR ---
            if st.button("🔎 Gerar Análise de Mercado", type="primary"):
                
                with st.spinner("Cruzando dados dos concorrentes..."):
                    # Busca dados no banco
                    query = supabase.table('historico_concorrentes').select("*").in_('data_registro', [str(data_base), str(data_atual)])
                    
                    if filtro_concorrentes:
                        query = query.in_('concorrente', filtro_concorrentes)
                    
                    df_dados = pd.DataFrame(query.execute().data)

                    if not df_dados.empty:
                        # Prepara DataFrames
                        df_dados['data_registro'] = pd.to_datetime(df_dados['data_registro']).dt.date
                        
                        df_hoje = df_dados[df_dados['data_registro'] == data_atual].set_index(['gtin', 'concorrente'])
                        df_antes = df_dados[df_dados['data_registro'] == data_base].set_index(['gtin', 'concorrente'])
                        
                        # Cruza as informações (Inner Join)
                        df_final = df_hoje.join(df_antes, lsuffix='_hj', rsuffix='_ant', how='inner').reset_index()
                        
                        # Cálculos
                        df_final['diff_preco'] = df_final['preco_hj'] - df_final['preco_ant']
                        df_final['variacao_pct'] = ((df_final['preco_hj'] - df_final['preco_ant']) / df_final['preco_ant']) * 100
                        
                        # Renomear colunas para ficar amigável
                        df_display = df_final.rename(columns={
                            'titulo_hj': 'Produto',
                            'concorrente': 'Concorrente',
                            'preco_ant': 'Preço ANTES',
                            'preco_hj': 'Preço AGORA',
                            'estoque_hj': 'Estoque Atual',
                            'vendas_unid_hj': 'Vendas (Unid)',
                            'marca_hj': 'Marca'
                        })

                        # --- KPI CARDS (RESUMO) ---
                        total_prods = len(df_display)
                        subiu = len(df_display[df_display['diff_preco'] > 0.1])
                        caiu = len(df_display[df_display['diff_preco'] < -0.1])
                        
                        k1, k2, k3 = st.columns(3)
                        k1.metric("Produtos Analisados", total_prods)
                        k2.metric("Subiram Preço 🟢", subiu, delta="Oportunidade")
                        k3.metric("Baixaram Preço 🔴", caiu, delta="- Cuidado", delta_color="inverse")
                        
                        st.divider()

                        # --- ABAS DE RESULTADO ---
                        tab1, tab2, tab3 = st.tabs(["📈 Variação de Preço (Oportunidades)", "🏆 Top 50 Mais Vendidos", "🚨 Estoque Zerado"])

                        # ---------------------------------------------------------
                        # ABA 1: VARIAÇÃO DE PREÇO (O QUE MUDOU)
                        # ---------------------------------------------------------
                        with tab1:
                            st.subheader("Quem mudou de preço?")
                            
                            # Filtra só quem teve mudança de preço
                            df_var = df_display[df_display['diff_preco'] != 0].copy()
                            
                            if not df_var.empty:
                                # Ordena: Quem aumentou mais primeiro
                                df_var = df_var.sort_values(by='variacao_pct', ascending=False)
                                
                                # Seleciona colunas úteis
                                cols_view = ['Concorrente', 'Produto', 'Preço ANTES', 'Preço AGORA', 'variacao_pct', 'Estoque Atual']
                                
                                # Aplica formatação de cores e dinheiro
                                st.dataframe(
                                    df_var[cols_view].style
                                    .format({
                                        'Preço ANTES': 'R$ {:.2f}',
                                        'Preço AGORA': 'R$ {:.2f}',
                                        'variacao_pct': '{:+.2f}%',
                                        'Estoque Atual': '{:.0f}'
                                    })
                                    .map(lambda x: 'color: green; font-weight: bold' if x > 0 else 'color: red; font-weight: bold', subset=['variacao_pct']),
                                    use_container_width=True,
                                    height=600
                                )
                            else:
                                st.info("Nenhuma alteração de preço detectada entre essas datas.")

                        # ---------------------------------------------------------
                        # ABA 2: TOP 50 VENDIDOS (Geral do Mercado)
                        # ---------------------------------------------------------
                        with tab2:
                            st.subheader(f"🏆 Top 50 Mais Vendidos em {data_atual}")
                            
                            # Pega os dados apenas de hoje e ordena por vendas
                            df_top = df_display.sort_values(by='Vendas (Unid)', ascending=False).head(50)
                            
                            st.dataframe(
                                df_top[['Produto', 'Concorrente', 'Preço AGORA', 'Vendas (Unid)', 'Estoque Atual']].style
                                .format({
                                    'Preço AGORA': 'R$ {:.2f}',
                                    'Vendas (Unid)': '{:.0f}',
                                    'Estoque Atual': '{:.0f}'
                                })
                                .background_gradient(subset=['Vendas (Unid)'], cmap='Greens'),
                                use_container_width=True
                            )

                        # ---------------------------------------------------------
                        # ABA 3: ESTOQUE ZERADO (BUYBOX)
                        # ---------------------------------------------------------
                        with tab3:
                            st.subheader("🚨 Produtos que ZERARAM no Concorrente")
                            
                            # Filtra: Tinha estoque antes (>0) e agora é 0
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
                                st.success("Nenhum concorrente zerou estoque importante hoje.")

                    else:
                        st.warning("Não encontrei dados suficientes para cruzar essas duas datas. Tente datas diferentes.")

        else:
            st.info("👋 Bem-vindo! Use o menu lateral para subir sua primeira planilha do Nubmetrics.")

    except Exception as e:
        st.error(f"Erro ao carregar sistema: {e}")
else:
    st.stop()
