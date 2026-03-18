import json

# JSON Schema для response_format
json_schema = {
    "name": "hip_dysplasia_analysis",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "request_id": {"type": "integer"},
            "type_of_diagnosis": {"type": "string"},
            "accurate_diagnosis": {"type": "string"},
            "description": {"type": "string"},
            "has_coxae_angulus": {"type": "boolean"},
            "coxae_angulus": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "left": {"$ref": "#/$defs/angle"},
                    "right": {"$ref": "#/$defs/angle"},
                },
                "required": ["left", "right"],
            },
            "landmarks": {"type": "array", "items": {"$ref": "#/$defs/landmark"}},
            "lines": {"type": "array", "items": {"$ref": "#/$defs/line"}},
        },
        "required": [
            "request_id",
            "type_of_diagnosis",
            "accurate_diagnosis",
            "description",
            "has_coxae_angulus",
            "landmarks",
            "lines",
        ],
        "$defs": {
            "point": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
            },
            "angle": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "vertex": {"$ref": "#/$defs/point"},
                    "arm1": {"$ref": "#/$defs/point"},
                    "arm2": {"$ref": "#/$defs/point"},
                },
                "required": ["vertex", "arm1", "arm2"],
            },
            "landmark": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "radius": {"type": "number"},
                    "label": {"type": "string"},
                },
                "required": ["x", "y", "radius", "label"],
            },
            "line": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "start": {"$ref": "#/$defs/point"},
                    "end": {"$ref": "#/$defs/point"},
                    "label": {"type": "string"},
                },
                "required": ["start", "end", "label"],
            },
        },
    },
}


# Пример использования с LiteLLM или аналогичной библиотекой
def make_request_with_json_schema():
    """
    Пример вызова API с response_format в виде json_schema

    В зависимости от используемой библиотеки (LiteLLM, OpenAI SDK и т.д.)
    синтаксис может отличаться:

    LiteLLM пример:
    completion = litellm.completion(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Анализ изображения..."}],
        response_format={
            "type": "json_schema",
            "json_schema": json_schema  # переменная с определением схемы
        }
    )

    OpenAI SDK пример (beta):
    from openai import OpenAI
    client = OpenAI()
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Анализ изображения..."}],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "hip_dysplasia_analysis",
                "strict": True,
                "schema": json_schema["schema"]  # передаем только схему
            }
        }
    )

    return completion
    """
    pass


if __name__ == "__main__":
    print("JSON Schema загружена и доступна в переменной 'json_schema'")
    print(f"Name: {json_schema['name']}")
    print(f"Strict mode: {json_schema['strict']}")
    print("\nSchema structure:")
    print(json.dumps(json_schema["schema"], indent=2))
