O projeto está dividido em três componentes simples:

    indexar.py (O Cérebro): Lê os PDFs na tua área de trabalho, "parte-os" em pedaços pequenos e guarda-os numa base de dados inteligente. Durante este processo, usa IA para resumir os dados principais do concurso.

    watcher.py (O Vigilante): Um serviço que fica a correr em segundo plano. Sempre que colas um PDF novo na pasta, ele deteta-o e envia-o automaticamente para processamento. Não precisas de fazer nada manual.

    app.py (A Interface): Uma aplicação web (Streamlit) onde escolhes a pasta do concurso e conversas com os documentos através de um chat intuitivo. 
