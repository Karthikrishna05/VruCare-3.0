from functools import cache


@cache
def get_model(name, device):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(name, device=device)


def encode(texts, embedding_config):
    model = get_model(embedding_config["model"], embedding_config["device"])
    return model.encode(texts, batch_size=32).tolist()


def count_tokens(text, embedding_config):
    model = get_model(embedding_config["model"], embedding_config["device"])
    return len(model.tokenizer(text)["input_ids"])
