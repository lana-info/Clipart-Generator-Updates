import json
import ssl
import urllib.request
from pathlib import Path


def load_config():
    config_path = Path(__file__).with_name("config.json")
    return json.loads(config_path.read_text(encoding="utf-8"))


def post_json(url, headers, payload, timeout=25):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    config = load_config()
    api_key = str(config.get("kie_api_key", "")).strip()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    url = "https://api.kie.ai/api/v1/jobs/createTask"
    sample_url = "https://picsum.photos/768/768"
    cases = [
        ("gpt-image/1.5-text-to-image", {"prompt": "simple test image", "aspect_ratio": "1:1", "quality": "medium"}),
        ("gpt-image/1.5-image-to-image", {"prompt": "simple test image", "input_urls": [sample_url], "aspect_ratio": "1:1", "quality": "medium"}),
        ("flux-2/pro-text-to-image", {"prompt": "simple test image", "aspect_ratio": "1:1", "resolution": "1K"}),
        ("flux-2/flex-text-to-image", {"prompt": "simple test image", "aspect_ratio": "1:1", "resolution": "1K"}),
        ("flux-2/pro-image-to-image", {"prompt": "simple test image", "input_urls": [sample_url], "aspect_ratio": "1:1", "resolution": "1K"}),
        ("flux-2/flex-image-to-image", {"prompt": "simple test image", "input_urls": [sample_url], "aspect_ratio": "1:1", "resolution": "1K"}),
        ("google/nano-banana", {"prompt": "simple test image", "image_size": "1:1"}),
        ("google/nano-banana-edit", {"prompt": "simple test image", "image_urls": [sample_url], "image_size": "1:1"}),
        ("qwen/text-to-image", {"prompt": "simple test image", "image_size": "square_hd"}),
        ("qwen/image-to-image", {"prompt": "simple test image", "image_url": sample_url}),
    ]

    results = []
    for model_name, payload in cases:
        try:
            response = post_json(url, headers, {"model": model_name, "input": payload})
            results.append(
                {
                    "model": model_name,
                    "code": response.get("code"),
                    "msg": response.get("msg"),
                    "taskId": ((response.get("data") or {}).get("taskId")),
                    "payload": payload,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "model": model_name,
                    "error": str(exc),
                    "payload": payload,
                }
            )

    output_path = Path(__file__).with_name("target_probe_results.json")
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()