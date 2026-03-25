

## 🏗️Estrutura do Projeto
O sistema está dividido em três componentes principais que automatizam todo o fluxo de trabalho:

### 1. `indexar.py` (O Cérebro)
Este script é o motor de processamento. Ele lê os ficheiros PDF, limpa o texto e prepara os dados para a IA.
* **Extração Inteligente**: Utiliza o modelo **GPT-4o-mini** para ler a primeira página e identificar imediatamente a **Entidade Adjudicante**, o **Valor Base** e o **Prazo**.
* **Segmentação Jurídica**: Divide o texto em blocos (*chunks*) respeitando a estrutura de artigos e cláusulas para não perder o contexto legal.
* **Enriquecimento**: Cada pedaço de texto é guardado com os metadados do concurso, permitindo respostas precisas sobre valores e prazos em qualquer parte do documento.

### 2. `watcher.py` (O Vigilante)
Um serviço de automação que elimina o trabalho manual de carregamento de dados.
* **Monitorização Ativa**: Vigia a pasta de PDFs em tempo real.
* **Mãos-Livres**: Sempre que um novo documento é colado na pasta (ou uma subpasta é criada), o "Vigilante" deteta a alteração e inicia a indexação automaticamente.

### 3. `app.py` (A Interface)
Uma aplicação web intuitiva (Streamlit) para interação com os dados.
* **Contexto Isolado**: Podes selecionar pastas específicas para garantir que a IA apenas responde com base nos documentos daquele concurso.
* **Chat com Histórico**: O sistema recorda o que foi dito anteriormente, permitindo perguntas de seguimento.
* **Citação de Fontes**: Todas as respostas incluem o nome do ficheiro e a página, garantindo que a informação pode ser auditada.

---

##  Tecnologia e Inteligência

Para garantir eficiência e precisão técnica, o sistema utiliza:

* **Modelo de Linguagem (LLM)**: `gpt-4o-mini` da OpenAI. Escolhido pelo seu raciocínio lógico apurado em textos técnicos e custo operacional reduzido.
* **Embeddings (Representação Matemática)**: `text-embedding-3-small`. Este modelo converte o texto em vetores de 512 dimensões, permitindo que a IA encontre informação por **conceito** e não apenas por palavras-chave.
* **Base de Dados Vetorial**: **Supabase (PostgreSQL + pgvector)**. Os documentos são armazenados numa infraestrutura cloud segura, permitindo pesquisas semânticas ultra-rápidas.

---

