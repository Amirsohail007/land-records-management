# Land Records Management

## Overview

The Land Records Management project is a Python-based system for managing and extracting land record data. It integrates CRUD (Create, Read, Update, Delete) operations with web scraping to maintain up-to-date records. The system uses SQLAlchemy for database interactions and Scrapy for data extraction.

## Features

- **CRUD Operations**: Manage land record entries using SQLAlchemy.
- **Data Extraction**: Scrape land record data from a web source if not available in the database.
- **Command-Line Interface**: Run scripts with various arguments to control data extraction and refresh behavior.

## Prerequisites and Dependencies

Before you begin, ensure you have the following installed:

- Python 3.x
- Required Python packages (listed in `requirements.txt`)

## Installation

1. **Clone the Repository**

    ```sh
    git clone https://github.com/Amirsohail007/land-records-management.git
    ```

2. **Navigate to the Project Directory**

    ```sh
    cd land-records-management
    ```

3. **Install Required Packages**

    ```sh
    pip install -r requirements.txt
    ```

## Usage

### Running the Script

To run the main script and manage land records, use the command-line interface with the following options:

- `--district_name`: Name of the district (required)
- `--sub_district_name`: Name of the sub-district (required)
- `--village_name`: Name of the village (required)
- `--khasra_no`: The Khasra number (required)
- `--force_refresh`: Optional flag to force refresh existing data

### Example Commands

- **Extract and Save Data**

    ```sh
    python main.py --district_name 'नुह' --sub_district_name 'नगीना' --village_name 'F. pur dehar' --khasra_no '1//17' --force_refresh
    ```

- **Retrieve Data Without Refreshing**

    ```sh
    python main.py --district_name 'नुह' --sub_district_name 'नगीना' --village_name 'F. pur dehar' --khasra_no '1//17'
    ```

### How It Works

1. **Extract Data**: If data is not present in the database or if `--force_refresh` is specified, the script will scrape data from the web source.
2. **Save Data**: The script saves the extracted data into the database.
3. **Read Data**: Retrieve existing records from the database as needed.

## Project Structure

- **`requirements.txt`**: Lists the Python packages required for the project.
- **`main.py`**: The main script for data extraction and CRUD operations.
- **`land_record_crud.py`**: Contains CRUD operations for managing land records.

### Contributing

Feel free to contribute to this project by submitting issues or pull requests. Contributions that improve functionality, fix bugs, or enhance documentation are welcome.

### License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details. You can also view the full license at [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).

### Contact

For any questions or suggestions, please open an issue on the [GitHub repository](https://github.com/Amirsohail007/land-records-management).
