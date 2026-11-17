import argparse
import json

import psycopg

from app.core.config import settings
from app.repositories.fragments import (
    search_by_text,
    search_by_vector,
    search_hybrid,
)
from app.services.embeddings import embed_query


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument(
        "--mode",
        choices=["vector", "text", "hybrid"],
        default="hybrid",
    )
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    with psycopg.connect(settings.database_url) as conn:
        if args.mode == "text":
            results = search_by_text(
                conn,
                query=args.query,
                limit=args.limit,
            )
        else:
            vector = embed_query(args.query)

            if args.mode == "vector":
                results = search_by_vector(
                    conn,
                    query_embedding=vector,
                    limit=args.limit,
                )
            else:
                results = search_hybrid(
                    conn,
                    query=args.query,
                    query_embedding=vector,
                    limit=args.limit,
                )

    for row in results:
        row["score"] = float(row["score"])

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
