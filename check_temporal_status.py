import asyncio

from temporalio.client import Client


async def main():
    client = await Client.connect("localhost:7233")
    handle = client.get_workflow_handle("card-test-001")
    description = await handle.describe()

    print("Workflow ID:", description.id)
    print("Status:", description.status)


if __name__ == "__main__":
    asyncio.run(main())
