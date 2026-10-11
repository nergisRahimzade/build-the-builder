"""List available text builder models; never changes the Freya phone model."""
from openai import OpenAI

if __name__ == "__main__":
    print("\n".join(sorted(model.id for model in OpenAI().models.list()
                          if model.id.startswith("gpt-5") and not any(word in model.id for word in ("audio", "realtime", "search", "image")))))
