# 💰 Family Finance — Backend

Backend do **Family Finance**, um projeto open source de organização financeira pessoal e familiar.

A proposta é permitir que qualquer pessoa com conhecimento básico de desenvolvimento consiga criar sua própria instância do sistema utilizando, para uso pessoal e testes, uma stack que pode ser mantida praticamente sem custo:

- ⚡ **FastAPI** — API backend
- 🗄️ **PostgreSQL / Supabase** — banco de dados
- 🏦 **Pluggy + MeuPluggy** — conexão com dados financeiros via Open Finance
- ☁️ **Render** — hospedagem do backend
- 📱 **Flutter** — aplicativo mobile, mantido em um repositório separado

> ⚠️ **Importante:** este projeto foi pensado inicialmente para uso pessoal/familiar. Antes de disponibilizá-lo comercialmente ou para muitos usuários, revise segurança, LGPD, infraestrutura, termos de uso da Pluggy e os limites dos planos utilizados.

---

## ✨ O que o backend faz

O backend é responsável por:

- 👤 cadastro e autenticação dos usuários;
- 🔐 emissão e validação de JWT;
- 🔌 comunicação segura com a API da Pluggy;
- 🎫 geração de Connect Tokens para o aplicativo;
- 🏦 registro das instituições conectadas;
- 💳 sincronização de contas bancárias;
- 💳 sincronização de cartões de crédito;
- 🔄 sincronização de transações;
- 📈 sincronização de investimentos;
- 🗃️ armazenamento de snapshots financeiros;
- ✍️ investimentos manuais;
- 📅 compromissos mensais manuais;
- 🗓️ períodos personalizados para consulta de cartões;
- 📡 disponibilização dos dados para o aplicativo Flutter.

### 🔒 Regra importante de segurança

As credenciais privadas da Pluggy ficam **somente no backend**.

Nunca coloque:

```text
PLUGGY_CLIENT_SECRET
```

dentro do aplicativo Flutter.

---

# 🧱 Arquitetura

Fluxo simplificado:

```text
┌────────────────────┐
│     📱 Flutter App │
└─────────┬──────────┘
          │ HTTPS
          ▼
┌────────────────────┐
│      ⚡ FastAPI    │
│      ☁️ Render     │
└──────┬───────┬─────┘
       │       │
       │       └──────────────► 🔌 Pluggy API
       │                         │
       │                         ▼
       │                    🏦 MeuPluggy
       │                         │
       │                         ▼
       │                  🏛️ Bancos / Open Finance
       │
       ▼
┌────────────────────┐
│ 🗄️ PostgreSQL     │
│ ☁️ Supabase        │
└────────────────────┘
```

---

# 1. 🧰 Pré-requisitos

Você precisará de:

- ✅ Git
- ✅ GitHub
- ✅ Python 3
- ✅ uma conta gratuita no Supabase;
- ✅ uma conta no MeuPluggy;
- ✅ uma conta de desenvolvedor no Dashboard da Pluggy;
- ✅ uma conta no Render.

Também será necessário utilizar o repositório Flutter do Family Finance para o aplicativo.

---

# 2. 📥 Faça um fork ou clone do projeto

Faça um fork deste repositório para a sua própria conta do GitHub.

Depois:

```bash
git clone SEU_REPOSITORIO
cd family-finance
```

Crie um ambiente virtual:

### 🪟 Windows

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 🍎🐧 Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Instale as dependências:

```bash
pip install -r requirements.txt
```

✅ Backend local preparado.

---

# 3. 🗄️ Criando o banco gratuitamente no Supabase

Crie uma conta no Supabase e depois:

1. ➕ crie um novo projeto;
2. 🏷️ escolha um nome;
3. 🔑 escolha uma senha forte para o banco;
4. ⏳ aguarde a criação do projeto;
5. 🔗 abra a opção **Connect** do projeto.

O backend utiliza PostgreSQL diretamente através do SQLAlchemy.

Para o setup utilizado neste projeto, você precisará das seguintes informações:

```text
DB_USER
DB_PASSWORD
DB_HOST
DB_PORT
DB_NAME
```

Uma configuração utilizando o Transaction Pooler normalmente terá formato semelhante a:

```text
Host:
aws-0-REGIAO.pooler.supabase.com

Port:
6543

Database:
postgres

User:
postgres.REFERENCIA_DO_PROJETO
```

A senha será a senha do banco definida no Supabase.

---

## 🧩 Tabelas

Você não precisa criar manualmente as tabelas para iniciar o projeto.

Ao iniciar o FastAPI, o SQLAlchemy executa a criação das tabelas declaradas nos models.

Atualmente são utilizadas tabelas como:

```text
users
pluggy_items
financial_snapshots
monthly_manual_commitments
monthly_card_periods
manual_investments
```

Depois que o backend iniciar pela primeira vez, você poderá visualizá-las no **Table Editor** do Supabase.

> 💡 Na primeira execução, basta o backend conseguir se conectar corretamente ao banco.

---

# 4. 🏦 Configurando o MeuPluggy

O MeuPluggy é usado para que você tenha controle sobre os consentimentos Open Finance das suas próprias contas.

Crie uma conta no **MeuPluggy**.

Depois:

1. entre na plataforma;
2. escolha **Conectar conta**;
3. selecione seu banco;
4. realize o fluxo de autorização do Open Finance;
5. autorize o compartilhamento das informações desejadas;
6. repita para cada instituição financeira que deseja utilizar.

Exemplos:

```text
🏦 MeuPluggy
├── Nubank
├── C6 Bank
├── PicPay
├── Itaú
└── outras instituições
```

O consentimento é feito diretamente dentro do fluxo do banco.

> 🔐 O Family Finance não recebe sua senha bancária.

---

# 5. 🔌 Criando a aplicação no Dashboard da Pluggy

Além do MeuPluggy, você precisa criar uma conta no **Dashboard de desenvolvedores da Pluggy**.

No Dashboard:

1. 👥 crie seu Team;
2. 🧩 acesse **Applications**;
3. 🧪 utilize o ambiente **Development**;
4. ➕ crie uma Application;
5. 📋 copie:

```text
CLIENT_ID
CLIENT_SECRET
```

Essas credenciais serão utilizadas pelo backend.

> 🚨 **Nunca publique o CLIENT_SECRET no GitHub.**

---

# 6. 🔗 Habilitando o conector MeuPluggy

Na aplicação de desenvolvimento da Pluggy, habilite o conector:

```text
MeuPluggy
```

Depois utilize a opção de Demo/Preview da aplicação para testar a conexão.

No Pluggy Connect:

1. escolha **MeuPluggy**;
2. faça login na sua conta MeuPluggy;
3. autorize o acesso;
4. selecione a instituição desejada.

Se você possui vários bancos conectados ao MeuPluggy, poderá ser necessário autorizar cada conexão.

Quando uma conexão é criada, a Pluggy gera um:

```text
Item ID
```

No Family Finance esse Item é registrado automaticamente quando a conexão é realizada pelo aplicativo.

---

# 7. ⚙️ Variáveis de ambiente

Crie um arquivo:

```text
.env
```

na raiz do backend.

Exemplo:

```env
DB_USER=postgres.SEU_PROJECT_REF
DB_PASSWORD=SUA_SENHA_DO_SUPABASE
DB_HOST=aws-0-SUA-REGIAO.pooler.supabase.com
DB_PORT=6543
DB_NAME=postgres

SECRET_KEY=COLOQUE_UMA_CHAVE_ALEATORIA_LONGA
ACCESS_TOKEN_EXPIRE_MINUTES=10080

PLUGGY_CLIENT_ID=SEU_CLIENT_ID
PLUGGY_CLIENT_SECRET=SEU_CLIENT_SECRET
```

---

## 🔐 Gerando uma SECRET_KEY

Você pode gerar uma chave com Python:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Copie o resultado para:

```env
SECRET_KEY=...
```

> 🚫 Nunca faça commit do `.env`.

---

# 8. ▶️ Rodando localmente

Execute:

```bash
uvicorn app.main:app --reload
```

A API ficará normalmente em:

```text
http://127.0.0.1:8000
```

### 📚 Documentação Swagger

```text
http://127.0.0.1:8000/docs
```

### ❤️ Health Check

Teste também:

```text
GET /health
```

Uma resposta válida será semelhante a:

```json
{
  "status": "ok",
  "database": "connected"
}
```

Se apareceu isso, ótimo:

```text
✅ FastAPI
✅ PostgreSQL
✅ Supabase
```

---

# 9. ☁️ Deploy gratuito no Render

Crie uma conta no Render.

Depois:

1. faça push do seu fork para o GitHub;
2. no Render selecione **New → Web Service**;
3. conecte seu GitHub;
4. escolha o repositório do backend;
5. escolha Python;
6. escolha o plano gratuito, caso ainda esteja disponível para sua conta.

Configure:

### 🔨 Build Command

```bash
pip install -r requirements.txt
```

### 🚀 Start Command

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

---

# 10. 🔑 Variáveis de ambiente no Render

Em **Environment**, adicione:

```text
DB_USER
DB_PASSWORD
DB_HOST
DB_PORT
DB_NAME
SECRET_KEY
ACCESS_TOKEN_EXPIRE_MINUTES
PLUGGY_CLIENT_ID
PLUGGY_CLIENT_SECRET
```

Utilize os mesmos valores configurados localmente.

> 🔐 Não coloque essas informações diretamente no código.

---

# 11. 🚀 Primeiro deploy

Depois de salvar o serviço, o Render fará:

```text
GitHub
   ↓
🔨 Build
   ↓
📦 pip install
   ↓
⚡ FastAPI
   ↓
🗄️ Conexão Supabase
   ↓
🚀 Deploy
```

Ao final você receberá uma URL semelhante a:

```text
https://seu-family-finance.onrender.com
```

Teste:

```text
https://seu-family-finance.onrender.com/health
```

Se retornar:

```text
status: ok
database: connected
```

🎉 Seu backend está online.

---

# 12. ⚠️ Atenção ao Supabase Pooler

Este projeto utiliza `psycopg` e foi preparado para funcionar com o Transaction Pooler do Supabase.

O código desabilita prepared statements automáticos:

```python
connect_args={
    "client_encoding": "utf8",
    "prepare_threshold": None,
}
```

Isso é importante quando o backend utiliza o pooler na porta:

```text
6543
```

> ⚠️ Não remova essa configuração sem entender o comportamento do pooler.

---

# 13. 📱 Conectando o Flutter ao backend

Depois que o Render estiver funcionando, copie sua URL:

```text
https://SEU-BACKEND.onrender.com
```

No projeto Flutter abra:

```text
lib/config/api_config.dart
```

e altere:

```dart
static const String baseUrl =
    "https://SEU-BACKEND.onrender.com";
```

Depois compile novamente o aplicativo.

---

# 14. 🔄 Como a conexão bancária funciona

Quando o usuário toca em conectar instituição:

```text
📱 Flutter
   ↓
POST /pluggy/connect-token
   ↓
⚡ FastAPI
   ↓
🔐 CLIENT_ID + CLIENT_SECRET
   ↓
🔌 Pluggy
   ↓
🎫 Connect Token
   ↓
📱 Flutter abre Pluggy Connect
   ↓
🏦 Usuário escolhe MeuPluggy
   ↓
✅ Autoriza conexão
   ↓
🔌 Pluggy cria Item
   ↓
📤 Flutter envia Item ID ao backend
   ↓
💾 Backend sincroniza os dados
```

O `CLIENT_SECRET` nunca precisa sair do backend.

---

# 15. 🔄 Atualização dos dados

O backend mantém um snapshot dos dados financeiros.

Entre eles:

- 🏦 contas;
- 💰 saldos;
- 🔁 transações;
- 💳 cartões;
- 📈 investimentos.

Ao solicitar uma atualização, o backend consulta novamente a Pluggy e atualiza o snapshot.

Existe um cooldown para evitar atualizações excessivas.

---

# 16. ⚠️ Limitações

Open Finance não garante que todas as instituições forneçam exatamente os mesmos dados.

Por exemplo:

- alguns bancos fornecem mais detalhes de cartão;
- alguns fornecem menos informações de parcelas;
- investimentos podem variar por instituição;
- determinados dados podem demorar para atualizar.

> 🧠 Portanto, diferenças entre bancos não significam necessariamente erro do Family Finance.

---

# 17. 🆓 Sobre os planos gratuitos

Este projeto foi estruturado para funcionar como projeto pessoal/hobby utilizando opções gratuitas disponíveis nos serviços utilizados.

Entretanto:

- ⏳ limites podem mudar;
- 💳 planos podem mudar;
- 🧪 períodos de trial podem mudar;
- 💤 serviços gratuitos podem entrar em modo de suspensão;
- 🔌 APIs externas podem alterar políticas.

Sempre consulte os planos atuais de:

- Pluggy;
- MeuPluggy;
- Supabase;
- Render.

Para uso comercial ou com grande número de usuários, considere infraestrutura e planos adequados.

---

# 18. 🔒 Segurança

Nunca publique:

```text
PLUGGY_CLIENT_SECRET
DB_PASSWORD
SECRET_KEY
tokens JWT
credenciais bancárias
```

Mantenha `.env` no `.gitignore`.

> 🚨 Se uma credencial privada for publicada por engano, revogue-a imediatamente.

---

# 19. 📂 Estrutura resumida

```text
family-finance/
│
├── 📁 app/
│   ├── routers/
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── security.py
│   ├── pluggy_client.py
│   └── main.py
│
├── requirements.txt
├── .env.example
└── README.md
```

---

# 20. 🏁 Próximo passo

Depois do backend funcionando:

1. 📱 configure o aplicativo Flutter;
2. 🔗 altere a URL da API;
3. 🔨 compile;
4. 👤 crie sua conta no Family Finance;
5. 🏦 conecte o MeuPluggy;
6. 🔄 sincronize seus bancos;
7. 💰 comece a utilizar o sistema.

---

## ⚖️ Aviso

Este projeto não é um produto oficial da Pluggy, Supabase, Render ou de qualquer instituição financeira.

Ele utiliza serviços e APIs dessas plataformas para fins de organização financeira pessoal.

Use por sua conta e risco e revise as políticas dos serviços antes de armazenar dados financeiros de terceiros.
