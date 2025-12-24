import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime

# --- CONEXÃO ---
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

st.set_page_config(page_title="Radar ML - Perfumes", layout="wide")
st.title("🕵️ Radar de Concorrência - Perfumes")

# --- BARRA LATERAL (UPLOAD) ---
with st.sidebar:
    st.header("Upload de Dados")
    uploaded_file = st.file_uploader("Arquivo Nubmetrics (.csv/.xlsx)")
    data_ref = st.date_input("Data destes dados", datetime.now())
    
    nome_padrao = ""
    if uploaded_file:
        nome_padrao = uploaded_file.name.split('.')[0].replace("PERFUMES_", "").split(" - ")[0]
    concorrente_input = st.text_input("Nome Concorrente", value=nome_padrao)

    if st.button("Salvar no Banco Online"):
        if uploaded_file and concorrente_input:
            with st.spinner("Enviando para o Supabase..."):
                try:
                    try:
                        df = pd.read_csv(uploaded_file)
                    except:
                        df = pd.read_excel(uploaded_file)
                    
                    dados_envio = []
                    for _, row in df.iterrows():
                        p = pd.to_numeric(row.get('Preço Médio'), errors='coerce')
                        e = pd.to_numeric(row.get('Estoque'), errors='coerce')
                        
                        dados_envio.append({
                            "data_registro": str(data_ref),
                            "concorrente": concorrente_input,
                            "titulo": str(row.get('Título', ''))[:200],
                            "gtin": str(row.get('GTIN', '')).replace('.0', '').strip(),
                            "marca": str(row.get('Marca', '')),
                            "preco": float(p) if pd.notnull(p) else 0.0,
                            "estoque": int(e) if pd.notnull(e) else 0,
                            "vendas_unid": int(row.get('Vendas em Unid.', 0)),
                            "sku_concorrente": str(row.get('SKU', ''))
                        })
                    
                    chunk_size = 1000
                    for i in range(0, len(dados_envio), chunk_size):
                        supabase.table('historico_concorrentes').insert(dados_envio[i:i+chunk_size]).execute()
                        
                    st.success(f"✅ Sucesso! {len(dados_envio)} produtos salvos.")
                except Exception as e:
                    st.error(f"Erro: {e}")

# --- RELATÓRIOS ---
st.divider()
st.header("📊 Painel de Estratégia")

try:
    df_meta = pd.DataFrame(supabase.table('historico_concorrentes').select("concorrente, data_registro").execute().data)
    
    if not df_meta.empty:
        df_meta['data_registro'] = pd.to_datetime(df_meta['data_registro']).dt.date
        lista_datas = sorted(df_meta['data_registro'].unique(), reverse=True)
        lista_concorrentes = sorted(df_meta['concorrente'].unique())
        
        # Seleção automática das datas (Hoje vs Ontem)
        idx_anterior = 1 if len(lista_datas) > 1 else 0

        with st.expander("🔍 Configurações da Análise", expanded=True):
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1:
                filtro_concorrentes = st.multiselect("Concorrentes", lista_concorrentes)
            with c2:
                data_atual = st.selectbox("Data Recente", lista_datas, index=0)
            with c3:
                data_base = st.selectbox("Comparar com", lista_datas, index=idx_anterior)

        if st.button("🔎 Analisar Variação", type="primary"):
            query = supabase.table('historico_concorrentes').select("*").in_('data_registro', [str(data_base), str(data_atual)])
            if filtro_concorrentes:
                query = query.in_('concorrente', filtro_concorrentes)
            
            df_dados = pd.DataFrame(query.execute().data)

            if not df_dados.empty:
                df_dados['data_registro'] = pd.to_datetime(df_dados['data_registro']).dt.date
                df_fim = df_dados[df_dados['data_registro'] == data_atual].set_index(['gtin', 'concorrente'])
                df_inicio = df_dados[df_dados['data_registro'] == data_base].set_index(['gtin', 'concorrente'])
                
                df_final = df_fim.join(df_inicio, lsuffix='_fim', rsuffix='_ini', how='inner').reset_index()
                df_final['delta_preco'] = df_final['preco_fim'] - df_final['preco_ini']
                
                aumentos = df_final[df_final['delta_preco'] > 0.01].sort_values(by='delta_preco', ascending=False)
                if not aumentos.empty:
                    st.success(f"💎 {len(aumentos)} produtos subiram de preço!")
                    st.dataframe(aumentos[['concorrente', 'titulo_fim', 'preco_ini', 'preco_fim', 'estoque_fim']], use_container_width=True)
                else:
                    st.info("Ninguém subiu preço.")
                    
                quedas = df_final[df_final['delta_preco'] < -0.01]
                if not quedas.empty:
                    st.error(f"⚠️ {len(quedas)} produtos baixaram de preço!")
                    st.dataframe(quedas[['concorrente', 'titulo_fim', 'preco_ini', 'preco_fim']], use_container_width=True)
            else:
                st.warning("Sem dados suficientes.")
    else:
        st.info("Aguardando primeiro upload...")
except Exception as e:
    st.error(f"Conexão OK, mas sem dados ainda.")
