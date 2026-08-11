def summarize(values: list[int]) -> dict[str, float]:
    total = sum(values)
    return {
        "count": float(len(values)),
        "average": total / len(values) if values else 0.0,
    }


result = summarize([3, 5, 8, 13])
print(f"average={result['average']:.2f}")
