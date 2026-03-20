import csv

# Read the CSV file
posts = []
with open("social_posts.csv", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        impressions = int(row["impressions"])
        clicks = int(row["clicks"])
        ctr = (clicks / impressions) * 100  # CTR as a percentage
        posts.append({
            "id": row["post_id"],
            "platform": row["platform"],
            "content": row["content"],
            "impressions": impressions,
            "clicks": clicks,
            "ctr": ctr,
        })

# Sort by CTR, highest first
posts.sort(key=lambda p: p["ctr"], reverse=True)

# Print the ranked list
print(f"\n{'Rank':<5} {'CTR':>6}  {'Platform':<12} {'Clicks':>7} {'Impressions':>12}  Content")
print("-" * 90)
for rank, post in enumerate(posts, start=1):
    preview = post["content"][:45] + ("…" if len(post["content"]) > 45 else "")
    print(f"{rank:<5} {post['ctr']:>5.1f}%  {post['platform']:<12} {post['clicks']:>7,} {post['impressions']:>12,}  {preview}")

print()
