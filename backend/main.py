from fastapi import FastAPI

app = FastAPI(title="AI Reading Dashboard API")

@app.get("/")
def read_root():
    return {"status": "Backend, Neo4j, and Qdrant are active."}