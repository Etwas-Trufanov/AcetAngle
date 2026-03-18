# render_schema.py

render_schema = {
    "name": "image_rendering",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "landmarks": {
                "type": "array",
                "items": {
                    "$ref": "#/$defs/landmark"
                }
            },
            "lines": {
                "type": "array",
                "items": {
                    "$ref": "#/$defs/line"
                }
            },
            "angles": {
                "type": "array",
                "items": {
                    "$ref": "#/$defs/angle_with_label"
                }
            }
        },
        "required": ["landmarks", "lines", "angles"],

        "$defs": {
            "point": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2
            },

            "landmark": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "radius": {"type": "number"},
                    "label": {"type": "string"}
                },
                "required": ["x", "y", "radius", "label"]
            },

            "line": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "start": {"$ref": "#/$defs/point"},
                    "end": {"$ref": "#/$defs/point"},
                    "label": {"type": "string"}
                },
                "required": ["start", "end", "label"]
            },

            "angle_with_label": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "vertex": {"$ref": "#/$defs/point"},
                    "arm1": {"$ref": "#/$defs/point"},
                    "arm2": {"$ref": "#/$defs/point"},
                    "label": {"type": "string"}
                },
                "required": ["vertex", "arm1", "arm2", "label"]
            }
        }
    }
}