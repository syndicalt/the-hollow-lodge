from fastapi import FastAPI


app = FastAPI(
    title="The Hollow Lodge",
    version="0.1.0",
    summary="Authoritative server for The Hollow Lodge.",
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}

