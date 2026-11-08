import asyncio
from temporalio.client import Client

from app.temporal.workflows import CardWorkflow


async def main():
    client = await Client.connect("localhost:7233")

    result = await client.execute_workflow(
        CardWorkflow.run,
        args=[
            "Термокружка из нержавеющей стали, объём 500 мл, цвет чёрный.",
            3,
            "74b5f49db09a",
        ],
        id="card-test-003",
        task_queue="card-queue",
    )
    print("Workflow result:", result)


if __name__ == "__main__":
    asyncio.run(main())
