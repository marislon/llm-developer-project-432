import psycopg

from app.core.config import settings
from app.repositories.fragments import search_by_vector
from app.services.embeddings import embed_query

QUERIES = [
    "Электрический чайник",
    "Блендер",
    "Ёмкость для полутора литров воды",
    "KTL-1700",
    "BLD-800",
    "Зимняя женская куртка",
    "Бронирование гостиницы",
]


def main():
    with psycopg.connect(settings.database_url) as conn:
        for query in QUERIES:
            print(f"\nQUERY: {query}")
            print("-" * 80)

            vector = embed_query(query)

            results = search_by_vector(
                conn,
                query_embedding=vector,
                similarity_threshold=-1.0,
                limit=26,
            )

            for row in results:
                print(
                    f"{row['score']:.4f} | "
                    f"{row['text']}"
                )


if __name__ == "__main__":
    main()
