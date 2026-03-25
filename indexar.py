import os
import json
import time
import re
from pathlib import Path
from dotenv import load_dotenv

from pydantic import BaseModel, Field
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import SupabaseVectorStore
from supabase.client import Client, create_client

STATE_FILE = "processed_files.json"
BATCH_SIZE = 100
SLEEP_TIME = 2

# 1. Estrutura Pydantic para a Extração Via LLM (gpt-4o-mini)
class MetadadosConcurso(BaseModel):
    entidade_adjudicante: str = Field(description="Entidade principal (Ex: Câmara Municipal X)", default="Desconhecido")
    valor_base: str = Field(description="Valor do concurso (Ex: 150.000€)", default="Desconhecido")
    prazo_execucao: str = Field(description="Prazo indicado", default="Desconhecido")
    objeto_contrato: str = Field(description="Resumo do objeto do contrato", default="Desconhecido")

def load_processed_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {}

def save_processed_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4)
    except: pass

def extrair_metadados(texto_pagina: str, llm_structured) -> dict:
    """Extrai entidades usando o LLM super rápido da página principal do documento."""
    try:
        # Passa os primeiros ~4000 caracteres da 1ª página
        res = llm_structured.invoke(f"Extrai os dados precisos deste concurso público:\n\n{texto_pagina[:4000]}")
        # Convert Pydantic model to dictionary
        return res.model_dump() if hasattr(res, "model_dump") else res.dict()
    except Exception as e:
        print(f"Aviso extração: {e}")
        return {"entidade_adjudicante": "Desconhecido", "valor_base": "Desconhecido", "prazo_execucao": "Desconhecido", "objeto_contrato": "Desconhecido"}

def indexar_ficheiros():
    load_dotenv()
    
    supabase: Client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    
    # 2. Redução de Dimensões (ATENÇÃO: Requer update na tabela Supabase 'documents' -> vector(512))
    # Se der erro no Supabase, retira o parâmetro 'dimensions=512' para voltar a usar 1536
    embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small", dimensions=512)
    
    # 3. Preparação do Extrator de Metadados
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    llm_structured = llm.with_structured_output(MetadadosConcurso)

    caminho_base = Path.home() / "Desktop" / "pdfs"
    estado_ficheiros = load_processed_state()
    ficheiros_proc = 0

    # 4. Text Splitter otimizado focado em Documentos Jurídicos
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000, 
        chunk_overlap=200, 
        separators=["\nArtigo", "\nCláusula", "\n\n", "\n", ".", " ", ""]
    )

    print("Pesquisa de PDFs iniciada...")

    for subpasta in caminho_base.iterdir():
        if subpasta.is_dir():
            folder_id = str(subpasta.name) 
            
            for ficheiro_pdf in subpasta.glob("*.pdf"):
                caminho_str = str(ficheiro_pdf)
                try:
                    mtime = os.path.getmtime(caminho_str)
                    if caminho_str in estado_ficheiros and estado_ficheiros[caminho_str] == mtime:
                        continue
                        
                    print(f"\nA indexar: {ficheiro_pdf.name}")
                    
                    loader = PyMuPDFLoader(caminho_str)
                    docs = loader.load()
                    if not docs:
                        continue

                    # Extração Rápida de Metadados da 1ª Página (usando LLM)
                    novos_metadados = extrair_metadados(docs[0].page_content, llm_structured)
                    
                    # 5. Pré-processamento e Injeção de Metadados em todos os chunks
                    for doc in docs:
                        # Limpa quebras de linha que hifenizam palavras a meio (ex: impor-\ntante)
                        doc.page_content = re.sub(r"(\w+)-\n(\w+)", r"\1\2", doc.page_content)
                        
                        doc.metadata["folder_id"] = folder_id
                        if "page" in doc.metadata and isinstance(doc.metadata["page"], int):
                            doc.metadata["page"] += 1
                        
                        # Injeta a Entidade, Valor e Prazo nos metadados deste pedaço de texto!
                        doc.metadata.update(novos_metadados)

                    # Separa guiado pelas Regras/Regex
                    chunks = splitter.split_documents(docs)
                    print(f"   -> Foram gerados {len(chunks)} chunks.")
                    
                    for i in range(0, len(chunks), BATCH_SIZE):
                        batch = chunks[i:i+BATCH_SIZE]
                        SupabaseVectorStore.from_documents(
                            documents=batch,
                            embedding=embeddings_model,
                            client=supabase,
                            table_name="documents",
                            query_name="match_documents"
                        )
                        time.sleep(SLEEP_TIME)

                    estado_ficheiros[caminho_str] = mtime
                    save_processed_state(estado_ficheiros)
                    ficheiros_proc += 1
                    print(f"   -> Indexado com sucesso.")

                except Exception as e:
                    print(f"!!! Erro no ficheiro {caminho_str}: {e} !!!")

    print(f"\nResumo: {ficheiros_proc} ficheiros indexados e enriquecidos com LLM.")

if __name__ == "__main__":
    indexar_ficheiros()
