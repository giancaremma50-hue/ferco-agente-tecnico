from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic
import requests
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
GRAPH_TOKEN = os.environ.get("GRAPH_TOKEN")
DRIVE_ID = "b!wNYTLcG7JkKHlFrVh16nEDrsv8-mAvtOn2ATWHo6n5PIpybBbcMyQa18F2OyQWel"

SYSTEM_PROMPT = """Eres el Asistente Técnico de Ferco Cerámica Guatemala.
Ayudas a los nuevos ingresos del equipo comercial a entender los productos técnicamente.

Reglas:
1. Responde en español guatemalteco, tono de mentor técnico, nunca de chatbot.
2. Para preguntas conceptuales (¿qué es X?) responde con 3-5 oraciones claras y prácticas.
3. Si el usuario menciona un producto, marca, código SKU o categoría específica, al final incluye:
   [BUSCAR:término clave]
   Ejemplo: [BUSCAR:Power Vulcano] o [BUSCAR:piso SPC] o [BUSCAR:035849]
4. Para preguntas puramente conceptuales, NO incluyas [BUSCAR].
5. Nunca inventes especificaciones técnicas que no conozcas con certeza."""

class ChatRequest(BaseModel):
    message: str
    history: list = []

def search_sharepoint(query: str):
    if not GRAPH_TOKEN:
        return []
    url = "https://graph.microsoft.com/v1.0/search/query"
    headers = {
        "Authorization": f"Bearer {GRAPH_TOKEN}",
        "Content-Type": "application/json"
    }
    body = {
        "requests": [{
            "entityTypes": ["driveItem"],
            "query": {"queryString": f"{query} ficha técnica"},
            "from": 0,
            "size": 5,
            "fields": ["name", "webUrl", "parentReference", "createdDateTime"]
        }]
    }
    try:
        r = requests.post(url, headers=headers, json=body, timeout=10)
        data = r.json()
        hits = data.get("value", [{}])[0].get("hitsContainers", [{}])[0].get("hits", [])
        results = []
        for h in hits:
            resource = h.get("resource", {})
            name = resource.get("name", "")
            if name.lower().endswith(".pdf"):
                results.append({
                    "name": name,
                    "url": resource.get("webUrl", ""),
                    "category": resource.get("parentReference", {}).get("path", "").split("/PRODUCTOS/")[-1].split("/")[0]
                })
        return results
    except Exception as e:
        print(f"SharePoint error: {e}")
        return []

@app.get("/")
def root():
    return {"status": "Agente Técnico Ferco activo"}

@app.post("/chat")
def chat(req: ChatRequest):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    messages = req.history + [{"role": "user", "content": req.message}]

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=messages
    )

    reply = response.content[0].text
    fichas = []

    import re
    match = re.search(r'\[BUSCAR:([^\]]+)\]', reply)
    if match:
        search_term = match.group(1)
        fichas = search_sharepoint(search_term)
        reply = re.sub(r'\[BUSCAR:[^\]]+\]', '', reply).strip()

    return {
        "reply": reply,
        "fichas": fichas
    }
