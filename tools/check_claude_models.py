from anthropic import Anthropic

if __name__ == "__main__":
    print("\n".join(model.id for model in Anthropic().models.list()))
