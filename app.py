import streamlit as st
import os
from pathlib import Path
from dotenv import load_dotenv

from langchain_community.vectorstores import SupabaseVectorStore
from supabase.client import Client, create_client
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_classic.chains import create_retrieval_chain, create_history_aware_retriever
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate
from langchain_core.messages import HumanMessage, AIMessage

# Carregar variáveis de ambiente do ficheiro .env
load_dotenv()

# Verifica se a chave foi carregada
if not os.environ.get("OPENAI_API_KEY"):
    st.error("⚠️ A chave OPENAI_API_KEY não foi encontrada! Cria um ficheiro .env na pasta do projeto com a tua chave (ex: `OPENAI_API_KEY=sk-proj-...`).")
    st.stop()

@st.cache_resource
def load_db():
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
    
    if not supabase_url or not supabase_key:
        st.error("Erro: Por favor configure SUPABASE_URL e SUPABASE_SERVICE_KEY no ficheiro .env")
        st.stop()
        
    supabase: Client = create_client(supabase_url, supabase_key)
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small", dimensions=512)
    
    return SupabaseVectorStore(
        embedding=embeddings,
        client=supabase,
        table_name="documents",
        query_name="match_documents"
    )

from langchain_core.documents import Document
def _patched_sim_search(self, query: list[float], k: int, filter=None, postgrest_filter=None, score_threshold=None, **kwargs):
    match_documents_params = dict(query_embedding=query, match_count=k)
    if filter: 
        match_documents_params["filter"] = filter
    res = self._client.rpc(self.query_name, match_documents_params).execute()
    docs = []
    for s in res.data:
        if s.get("content"):
            meta = s.get("metadata", {})
            # Garantir chaves default para evitar KeyError no PromptTemplate de ficheiros antigos
            for key in ["entidade_adjudicante", "valor_base", "prazo_execucao", "objeto_contrato"]:
                meta.setdefault(key, "Não especificado")
            docs.append((Document(metadata=meta, page_content=s["content"]), s.get("similarity", 0.0)))
    return docs
SupabaseVectorStore.similarity_search_by_vector_with_relevance_scores = _patched_sim_search

db = load_db()

@st.cache_resource
def load_llm():
    return ChatOpenAI(model="gpt-4o-mini", temperature=0)

llm = load_llm()

st.set_page_config(page_title="RAG por Pastas", layout="wide")
st.title("Pesquisa Documental Compartimentada 📁")

caminho_base = Path.home() / "Desktop" / "pdfs"
pastas_disponiveis = []

if caminho_base.exists():
    for subpasta in caminho_base.iterdir():
        if subpasta.is_dir():
            pastas_disponiveis.append(subpasta.name)
    pastas_disponiveis.sort()
else:
    st.error(f"⚠️ Não foi possível encontrar a pasta principal em: {caminho_base}")

st.sidebar.header("Configurações")

if not pastas_disponiveis:
    st.sidebar.warning("Nenhuma subpasta encontrada dentro de 'pdfs'.")
    pasta_selecionada = None
else:
    pasta_selecionada = st.sidebar.selectbox("Seleciona o contexto:", pastas_disponiveis)
    st.sidebar.markdown(f"**Pasta ativa:** `{pasta_selecionada}`")

# ---------------------------------------------------------
# 1. Prompt para reformular a pergunta com base no histórico
contextualize_q_system_prompt = """Dada uma conversa de chat e a última pergunta do utilizador, \
que pode referenciar contexto do chat anterior, formula uma pergunta isolada que possa ser compreendida \
sem o histórico de chat. Não respondas à pergunta, apenas reformula-a se necessário, ou devolve-a como está."""

contextualize_q_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", contextualize_q_system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ]
)

# 2. Prompt principal de QA
qa_system_prompt = """És um consultor especialista em Contratação Pública. A tua função é analisar rigorosamente as peças de concursos públicos e extrair informações vitais.

O teu objetivo é responder à Pergunta do utilizador usando EXCLUSIVAMENTE a Informação Fornecida no Contexto.

DIRETRIZES DE COMPORTAMENTO:
1. ZERO ALUCINAÇÕES LEGAIS/FINANCEIRAS: Se a informação não constar no contexto fornecido, deves responder APENAS: "Essa informação não consta nos excertos recuperados." Nunca inventes valores.
2. USO DO CONTEXTO GLOBAL DO DOCUMENTO: Cada excerto fornecido vem precedido pelo "CONTEXTO DO CONCURSO" (Entidade Adjudicante, Valor Base, Prazo). Usa estes metadados INJETADOS para contextualizar a tua resposta e responder a perguntas globais, mesmo que o corpo principal do texto não fale sobre isso!
3. RESUMOS DO CONCURSO: Se o utilizador pedir um resumo ou visão geral, sintetiza cruzando o Contexto Global (Entidade/Valor/Prazo) com os detalhes extraídos dos textos.
4. FORMATAÇÃO CLARA: 
   - Usa listas com *bullet points* sempre que houver múltiplos critérios ou fases.
   - Usa **negrito** OBRIGATORIAMENTE para destacar prazos, valores financeiros e pesos de avaliação.
5. PROVA DOCUMENTAL: No final de cada facto, inclui a Fonte e a Página (ex: [Ficheiro.pdf | Pág. X]).

Informação Fornecida (Contexto e Excertos):
{context}"""

qa_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", qa_system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ]
)
# ---------------------------------------------------------

# Guardar histórico formatado para o LLM RAG
if "historico_chats_rag" not in st.session_state:
    st.session_state.historico_chats_rag = {}
    
# Guardar histórico para exibição de texto no Streamlit
if "historico_chats" not in st.session_state:
    st.session_state.historico_chats = {}

if pasta_selecionada:
    if pasta_selecionada not in st.session_state.historico_chats:
        st.session_state.historico_chats[pasta_selecionada] = []
        st.session_state.historico_chats_rag[pasta_selecionada] = []
    
    # Renderizar histórico visual
    for msg in st.session_state.historico_chats[pasta_selecionada]:
        st.chat_message(msg["role"]).write(msg["content"])

pergunta = st.chat_input(
    "O que queres saber sobre os documentos desta pasta?", 
    disabled=not pasta_selecionada
)

if pergunta and pasta_selecionada:
    st.chat_message("user").write(pergunta)
    st.session_state.historico_chats[pasta_selecionada].append({"role": "user", "content": pergunta})

    with st.chat_message("assistant"):
        with st.spinner(f"A pesquisar nos documentos da pasta {pasta_selecionada}..."):
            try:
                retriever = db.as_retriever(
                    search_type="similarity", 
                    search_kwargs={
                        "k": 10,       
                        "fetch_k": 30, 
                        "filter": {"folder_id": pasta_selecionada} 
                    }
                )

                # 1. Recuperador que entende o contexto das mensagens anteriores
                history_aware_retriever = create_history_aware_retriever(
                    llm, retriever, contextualize_q_prompt
                )

                # Formatamos os pedaços recebidos para incluir a origem e INJETAR os metadados do LLM
                document_prompt = PromptTemplate.from_template(
                    "--- [Origem: {source} | Pág: {page}] ---\n"
                    "CONTEXTO DO CONCURSO: Entidade Adjudicante: {entidade_adjudicante} | Valor: {valor_base} | Prazo: {prazo_execucao}\n"
                    "TEXTO:\n{page_content}\n"
                )

                # 2. Cadeia que junta os documentos e responde
                qa_chain = create_stuff_documents_chain(
                    llm, 
                    qa_prompt,
                    document_prompt=document_prompt
                )
                
                # 3. Cadeia final que liga tudo (Recuperação + Resposta)
                rag_chain = create_retrieval_chain(history_aware_retriever, qa_chain)

                # Passamos a pergunta E o histórico guardado (no formato do Langchain)
                resposta_obj = rag_chain.invoke({
                    "input": pergunta,
                    "chat_history": st.session_state.historico_chats_rag[pasta_selecionada]
                })

                resposta_texto = resposta_obj["answer"]
                st.write(resposta_texto)
                
                # Atualizar histórico para exibição (Simples texto)
                st.session_state.historico_chats[pasta_selecionada].append({"role": "assistant", "content": resposta_texto})
                
                # Atualizar histórico para o modelo (Objetos do Langchain)
                st.session_state.historico_chats_rag[pasta_selecionada].extend([
                    HumanMessage(content=pergunta),
                    AIMessage(content=resposta_texto)
                ])
                
                # ------ DEBUG TERMINAL ------
                print("\n" + "="*60)
                print(f"🐞 DEBUG RAG | PASTA ATIVA: [{pasta_selecionada}]")
                print("="*60)
                print(f"👤 PERGUNTA: {pergunta}\n")
                print("📄 CONTEXTO RECUPERADO (O que foi entregue ao LLM):")
                
                documentos = resposta_obj.get("context", [])
                
                if not documentos:
                    print("   ⚠️ AVISO: A pesquisa não encontrou nenhum pedaço de texto!")
                else:
                    for i, doc in enumerate(documentos):
                        origem = doc.metadata.get('source', 'Desconhecido').split('/')[-1]
                        texto_limpo = doc.page_content.replace('\n', ' ')
                        print(f"   [{i+1}] 📂 Ficheiro: {origem}")
                        print(f"       📝 Excerto: {texto_limpo[:200]}...")
                        print("-" * 40)
                
                print(f"\n🤖 RESPOSTA FINAL DO LLM: {resposta_texto}")
                print("="*60 + "\n")
                # -----------------------------
                
            except Exception as e:
                st.error(f"❌ Ocorreu um erro ao processar a resposta: {str(e)}")
