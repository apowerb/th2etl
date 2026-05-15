import os
from th2etl.storage import DatabaseStorage
from th2etl.configs.settings import get_settings

def main():
    print("Checking database state...")
    
    # Load environment variables from .env file if it exists
    from dotenv import load_dotenv
    load_dotenv()

    try:
        settings = get_settings()
        with DatabaseStorage.from_settings(settings) as storage:
            print("\n--- Blocs ---")
            blocs = storage.list_blocs()
            if blocs:
                for bloc in blocs:
                    print(f"- {bloc.name} (type: {bloc.bloc_type})")
            else:
                print("No blocs found.")

            print("\n--- Pipelines ---")
            pipelines = storage.list_pipelines()
            if pipelines:
                for pipeline in pipelines:
                    print(f"- {pipeline.name} (blocs: {pipeline.bloc_names})")
            else:
                print("No pipelines found.")

            print("\n--- Triggers ---")
            triggers = storage.list_triggers()
            if triggers:
                for trigger in triggers:
                    print(f"- {trigger.name} (cron: '{trigger.cron_expression}')")
            else:
                print("No triggers found.")

            print("\n--- Schedulers ---")
            schedulers = storage.list_schedulers()
            if schedulers:
                for scheduler in schedulers:
                    print(f"- {scheduler.name} (pipeline: {scheduler.pipeline_name}, trigger: {scheduler.trigger_name})")
            else:
                print("No schedulers found.")

    except Exception as e:
        print(f"\nAn error occurred: {e}")
        print("Please ensure your .env file is configured correctly with database connection details.")

if __name__ == "__main__":
    main()
