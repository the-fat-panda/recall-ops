# RecallOps

A self-improving incident-response agent. It remembers how past incidents were fixed. It recommends the fix with the best track record. Then it waits for a human to approve, runs it, and learns from the result.

Built for the CockroachDB and AWS hackathon. The agent's memory lives entirely in CockroachDB: its incident history, its vector embeddings, and even the checkpoint that lets a paused agent survive a restart.

## License

MIT. See [LICENSE](./LICENSE).

## The problem

A service breaks at 3am. The on-call engineer is usually solving a problem someone already solved six months ago. But that knowledge is scattered. It lives in old tickets, Slack threads, and people's heads. Nobody remembers that restarting the pod failed the last five times, and that a rollback fixed it every time.

RecallOps keeps that history in one place and puts it to work. It does not guess from a model's training data. It answers from what has actually worked on this kind of incident before. And it shows the numbers behind every recommendation, so a human can decide for themselves.

The memory has to be reliable, because an agent whose memory goes down does not degrade gracefully. It stops. That is why the memory layer is CockroachDB: distributed, always-on, and consistent, so the agent's history and its in-flight state are never lost.

## How it works: a walkthrough

Here is a real run, start to finish. The alert is a `CrashLoopBackOff` on a service called `orders-api`.

**1. The alert arrives.** Someone (or an alerting system) sends the agent an alert: `orders-api` has pods restarting repeatedly, back-off restarting a failed container, in production.

**2. Triage classifies it.** The agent makes one language-model call to read the alert and label it with a known incident signature. This one is classified as `CrashLoopBackOff`. In the same step, the agent opens a read-only connection to the live cluster through CockroachDB's Managed MCP Server and pulls a snapshot of the current state. Now the recommendation will be grounded in live reality, not just old history.

**3. Memory search finds similar incidents.** The agent turns the alert into a 768-dimension vector and runs a similarity search against CockroachDB's distributed vector index. It pulls back the past incidents that most resemble this one. This is the agent recognizing "I have seen this before."

**4. Reason scores the fixes.** For a `CrashLoopBackOff`, three fixes have been tried before: roll back to the prior revision, restart the pods, and restore a missing config key. The agent reads the real success and failure history for each one from CockroachDB and scores them. Rollback has a 100% success record. Restart has failed most times it was tried. The agent picks rollback. This step is deterministic. The model does not pick the winner. The recorded history does.

**5. Recommend explains the choice.** A second language-model call turns that decision into plain English: why rollback, and why not the others. It assembles an experience card that shows all the candidate fixes, their confidence scores, the failed history of restart, and the live evidence from step 2.

**6. The agent pauses and waits.** This is the important part. The agent stops at the recommendation and waits for a human to approve. Nothing touches the real service yet. The full state of the run is checkpointed into CockroachDB, and the request returns a thread id. The agent process is now free to end.

**7. A human approves, and the agent resumes.** The approval can come seconds or minutes later, as a completely separate request. It reconnects using the thread id, and the agent resumes the same run from the exact point it paused, reading its state back from CockroachDB. It runs the rollback against the service and then checks the service's health to confirm it actually recovered. In the demo, the sandbox flips from its broken version to its healthy one.

**8. The agent learns.** The outcome is written back to CockroachDB. Rollback's success count for `CrashLoopBackOff` goes up by one. The next time this incident appears, the recommendation is backed by one more real data point.

If step 4 turns up nothing confident, the agent does not invent a fix. It escalates and says a human is needed. An honest "I don't know" is a feature, not a failure. Send it a nonsense alert and it escalates cleanly instead of hallucinating an answer.

Only two of the eight steps call the language model: triage and recommend. Everything else is deterministic. This keeps the cost predictable and means any token spend can only come from two places in the code.

## Where CockroachDB does the work

CockroachDB is not a side store here. It is the entire memory layer, and it does five distinct jobs. Two of them are the hackathon's featured tools: the Distributed Vector Index and the Managed MCP Server.

**Distributed vector index for incident recall.** Past incidents are stored with 768-dimension embeddings in a vector column, indexed with CockroachDB's distributed vector indexing. A new alert is embedded and matched against that index with a similarity search. Because the vectors live in the same database as everything else, there is no separate vector store to run, no reindexing pain, and no gap between the embeddings and the operational data.

**Fix-history store for scoring.** A `fix_stats` table tracks how each fix has performed, per incident signature and per action. It counts how many times that fix succeeded and how many times it failed. The reason step reads these counts to score each candidate. This is the difference between "the model thinks a rollback might help" and "a rollback has resolved this exact incident 100% of the time across real attempts."

**Agent checkpoint store for the human-approval pause.** One of the most useful properties of the whole system: when the agent reaches the approval step, its entire state is checkpointed into CockroachDB. The request returns a thread id, and the process is free to end. The approval can arrive minutes later, as a separate request, and the agent resumes the same run from the exact point it paused. This was tested by killing the agent container between the recommendation and the approval. It still resumed cleanly, because the state was never held in memory. It was in CockroachDB. This is what lets the pause survive a crash, a restart, or a deploy, which is exactly the resilience an agent's memory needs.

**Managed MCP Server for live evidence.** During triage, the agent queries the cluster through CockroachDB's Managed MCP Server. The connection is read-only and safe by default, with no custom proxy to build. It snapshots the current cluster state and grounds the recommendation in live reality alongside the historical memory.

**The sandbox runs on CockroachDB.** The demo service (`orders-api`) that breaks and heals is itself backed by CockroachDB. So the whole loop touches the database, from evidence to execution to verification.

One database for all of this is a deliberate choice. Memory, history, and checkpoints belong together. Keeping them in a single distributed, transactional store means the agent's brain stays consistent and survivable, with nothing to stitch across three separate systems.

## From hackathon build to production

The demo proves the full loop against one real service. Here is how each piece grows into production.

**Reasoning already generalizes.** The system is seeded with several incident types, and each one has its own memory. Feed it a `CrashLoopBackOff` and it recalls that history and recommends a rollback. Feed it an `OOMKilled` and it recalls different history. It then recommends raising the memory limit, with its own confidence numbers. The reasoning scales through data. Every incident that flows through the system and gets resolved makes the memory richer. No code change is needed.

**Execution scales through a registry, not through rewrites.** Running a fix is handled by an executor registry. Each action maps to the runbook that performs it. In this build, one executor is installed and wired to the live sandbox. That lets the complete loop run end to end against a real service: decision, approval, execution, verification, and learning. Adding another action in production means registering another executor. Actions without a registered executor stop cleanly at the execution boundary and route to their existing production runbook. They are not faked, and they are not silently skipped. Reasoning scales through memory. Execution scales through modular executors. The prototype proves one executor against a live service.

**Adding a new incident type.** Triage classifies alerts into a known set of incident signatures. To add a new one, you extend the classification prompt with the new signature and seed its history into the database. It is a small, contained change in two known places, not a code rewrite across the system.

**Built for resilience and control.** The checkpoint-in-CockroachDB mechanism that powers the approval pause is the same mechanism a production system uses to survive restarts and resume long-running incident responses. It was built once and does double duty. Access to the API is protected by a shared key and per-IP rate limiting. Database access is restricted to the deployment host and runs over TLS with certificate verification. A cloud budget cap automatically cuts off the model provider if spend crosses a set threshold.

## Stack

- **Backend:** Python, FastAPI, LangGraph for the agent loop.
- **Language model:** Amazon Bedrock, reached through an OpenAI-compatible endpoint. Used only in triage and recommend.
- **Memory and checkpoints:** CockroachDB Cloud, with distributed vector indexing.
- **Live evidence:** CockroachDB Managed MCP Server, read-only.
- **Embeddings:** BGE, 768-dimension, run locally.
- **Frontend:** Vite and React, served by nginx.
- **Deployment:** Docker Compose, hosted on AWS EC2.

## CockroachDB tools used

- **Distributed Vector Indexing.** Incident embeddings (768-dimension) live in a vector column and are queried with similarity search to recall similar past incidents. This is the agent's long-term memory.
- **Managed MCP Server.** Used read-only during triage to snapshot live cluster state, so recommendations are grounded in the current system, not just history.

## AWS services used

- **Amazon Bedrock.** The foundation model behind the two language-model steps, triage and recommend. Triage classifies the alert; recommend explains the chosen fix.
- **Amazon EC2.** Hosts the full stack.

## Running it yourself

### Prerequisites

- Docker and the Docker Compose plugin.
- A CockroachDB Cloud cluster.
- Amazon Bedrock access through an OpenAI-compatible endpoint.

### 1. Get the code

```bash
git clone https://github.com/the-fat-panda/recall-ops.git
cd recall-ops
```

### 2. Place the database certificate

CockroachDB Cloud connects over TLS. Download your cluster's CA certificate and place it here:

```
./certs/root.crt
```

The `certs` directory is gitignored, so the certificate is never committed. Inside the containers this file is mounted at `/certs/root.crt`. That is the path the connection string expects.

### 3. Create the environment file

Create a file named `.env` in the project root. It is gitignored and must never be committed. These are the variables the app reads, with a note on each:

```
# CockroachDB connection string. Include the TLS settings and point
# sslrootcert at the in-container path, not a local path.
# Example tail: ...&sslmode=verify-full&sslrootcert=/certs/root.crt
DATABASE_URL=

# Amazon Bedrock, via the OpenAI-compatible endpoint.
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_PROJECT_ID=

# CockroachDB Managed MCP Server, for read-only live evidence.
COCKROACH_MCP_API_KEY=
COCKROACH_MCP_CLUSTER_ID=

# Where the agent reaches the sandbox service. Inside Compose this is the
# service name, for example http://orders-api:8080
ORDERS_API_URL=

# Shared access key that protects the API endpoints. Pick any long random
# string. Requests without it are rejected.
RECALLOPS_ACCESS_KEY=
```

Fill in each value. Leave nothing as a placeholder in the real file.

### 4. Start the stack

```bash
docker compose up -d --build
docker compose ps
```

You should see four services running: the agent API, the sandbox (`orders-api`), an idle operator container, and the frontend.

Open the app in a browser. Locally that is `http://localhost/`. If you deployed it to a server, use that server's address instead.

### 5. Seed the database (fresh database only)

Starting with an empty CockroachDB cluster? Load the incident history and fix stats once. The migration runs inside the seed command.

```bash
docker compose exec agent-api python -m backend.ingestion.seed
```

If the cluster is already seeded, skip this. Seeding again is not needed.

## Using it

Open the app and try an incident. The demo includes a few:

- A `CrashLoopBackOff` incident. It runs the full loop, heals the sandbox on approval, and records the outcome.
- An `OOMKilled` incident. It recalls a different memory and recommends a different fix, with its own confidence numbers.
- A nonsense incident. The agent escalates instead of inventing an answer.

Running the demo cold? Fire one throwaway query first to warm the model up. Then run the one you care about. A cold first call can behave differently.

## A note on the API key

The API endpoints (`/ask`, `/approve`, `/reset`) require a shared access key, sent as a header. The web app handles this for you as part of its normal request flow, so using the site just works. The key is there to stop scripts and bots from calling the API directly. To call the API directly yourself, send the key as the `X-API-Key` header.

## Repository layout

```
backend/
  agents/          The two model-backed steps, triage and recommend, plus the Bedrock client and prompts
  orchestration/   The LangGraph state machine: state, graph wiring, node functions, executor registry
  memory/          Vector search and fix scoring against CockroachDB
  ingestion/       Embedding and the seed script
  sandbox/         The orders-api demo service that breaks and heals
  mcp/             Read-only live-cluster evidence client
  schemas/         Data contracts between steps
  api/             FastAPI app, endpoints, rate limiting, access key
  infra/           Database connection and cert handling
  config/          Tunable thresholds in one place
frontend/          Vite and React app, nginx config
docker-compose.yml
certs/             TLS certificate (gitignored, place root.crt here)
.env               Secrets (gitignored, create your own)
```

## Security notes

- Secrets live only in `.env` and the `certs` directory. Both are gitignored and never committed to history.
- Database access is restricted to the deployment host and runs over TLS with certificate verification.
- The API is protected by a shared access key and per-IP rate limiting.
- A cloud budget cap automatically cuts off the model provider if spend crosses a set threshold.
