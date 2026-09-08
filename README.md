## Setup:
Para que o programa funcione corretamente, é necessário realizar os seguintes passos:
- **Acessar o link [fluxo viário do DETRAN](https://www.dados.df.gov.br/pt/dataset#/volume-diario-de-trafego-trechos-rodoviarios) e baixar algum dos .CSV de dados viários**
- **Incluir o arquivo baixado na pasta do projeto**
- **Renomear o arquivo baixado para 'Flow.csv'**

Além disso, importante atualizar os dados das tabelas 'trechos_com_coordenadas', e 'tomtom_flow', rodando os seguintes comandos:
```python
pip install pandas
export TOMTOM_API_KEY="chave da api aqui"
python mapping.py
python api-caller.py
```
