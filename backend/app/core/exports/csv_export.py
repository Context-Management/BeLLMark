"""CSV export — full tabular data with all metrics."""
import csv
import io


def generate_csv(data: dict) -> str:
    """Generate comprehensive CSV from prepared data. Returns CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)

    criteria = data["run"]["criteria"]
    weight_map = {c["name"]: c.get("weight", 1.0) for c in criteria}
    total_weight = sum(weight_map.values()) or 1.0

    # Header
    header = ["Question", "Model"]
    for c in criteria:
        header.append(c["name"])
    header.extend(["Average", "Weighted Score", "Tokens", "Latency (ms)", "Tok/s", "Cost ($)", "Status"])
    writer.writerow(header)

    # Data rows
    for q in data["questions"]:
        prompt = q["user_prompt"][:60] + "..." if len(q["user_prompt"]) > 60 else q["user_prompt"]

        # Collect scores per model from judgments
        model_scores = {}  # model_id -> criterion -> [scores]
        for jud in q["judgments"]:
            if jud["status"] == "success" and jud["scores"]:
                for mid_str, crit_scores in jud["scores"].items():
                    mid = int(mid_str) if isinstance(mid_str, str) else mid_str
                    if mid not in model_scores:
                        model_scores[mid] = {}
                    for crit, score in crit_scores.items():
                        model_scores[mid].setdefault(crit, []).append(score)

        for gen in q["generations"]:
            mid = gen["model_id"]
            row = [prompt, gen["model_name"]]

            # Criterion scores
            scores_for_model = model_scores.get(mid, {})
            avg_scores = []
            weighted_sum = 0
            for c in criteria:
                crit_scores = scores_for_model.get(c["name"], [])
                avg = sum(crit_scores) / len(crit_scores) if crit_scores else 0
                row.append(f"{avg:.1f}")
                avg_scores.append(avg)
                weighted_sum += avg * weight_map.get(c["name"], 1.0)

            # Average and weighted
            unweighted = sum(avg_scores) / len(avg_scores) if avg_scores else 0
            weighted = weighted_sum / total_weight
            row.append(f"{unweighted:.1f}")
            row.append(f"{weighted:.1f}")

            # Generation metrics
            row.append(gen["tokens"] or 0)
            row.append(gen["latency_ms"] or 0)
            tok_s = (gen["tokens"] / (gen["latency_ms"] / 1000)) if gen.get("tokens") and gen.get("latency_ms") and gen["latency_ms"] > 0 else 0
            row.append(f"{tok_s:.1f}")

            # Cost (proportional estimate)
            # Find model in models list
            model_data = next((m for m in data["models"] if m["id"] == mid), None)
            if model_data and model_data["total_tokens"] > 0 and model_data["estimated_cost"] > 0:
                cost_per_token = model_data["estimated_cost"] / model_data["total_tokens"]
                row.append(f"{(gen['tokens'] or 0) * cost_per_token:.4f}")
            else:
                row.append("0.0000")

            row.append(gen["status"])
            writer.writerow(row)

    return output.getvalue()
