import csv
import requests
import time
import logging
from datetime import datetime
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[
    logging.FileHandler("script.log"),
    logging.StreamHandler()
])

# Function to fetch teams (IDs and names) from the GitHub API with proper pagination handling
def fetch_teams(enterprise_slug, token):
    url = f"https://api.github.com/enterprises/{enterprise_slug}/teams?per_page=100"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    teams = []
    while url:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            teams.extend([{'id': team['id'], 'name': team['name']} for team in data])
            url = response.links.get('next', {}).get('url')  # Handle pagination
            if url:
                logging.info("Fetching next page of teams...")
        else:
            logging.error(f"Failed to fetch teams with status code {response.status_code}. Error: {response.text}")
            break  # Stop the loop if there's an error
    logging.info(f"Fetched {len(teams)} teams successfully.")
    return teams

# Function to fetch copilot usage data for a team
def fetch_copilot_usage(enterprise_id, team_id, token):
    url = f"https://api.github.com/enterprises/{enterprise_id}/team/{team_id}/copilot/usage"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"
    }
    
    retry_count = 0
    max_retries = 5
    
    while retry_count < max_retries:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            logging.info(f"Successfully fetched data for team {team_id}")
            return response.json()
        elif response.status_code == 403 and 'X-RateLimit-Remaining' in response.headers and int(response.headers['X-RateLimit-Remaining']) == 0:
            reset_time = int(response.headers['X-RateLimit-Reset'])
            wait_time = max(reset_time - int(time.time()), 0) + 1
            logging.warning(f"Rate limit exceeded. Waiting for {wait_time} seconds...")
            time.sleep(wait_time)
            retry_count += 1
        else:
            logging.error(f"Failed to fetch data for team {team_id}: {response.status_code}")
            if retry_count < max_retries:
                wait_time = 2 ** retry_count  # Exponential backoff
                logging.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                retry_count += 1
            else:
                return None

    return None

# Function to write data to a single CSV file
def write_to_csv(data):
    current_date = datetime.now().strftime("%Y-%m-%d")
    output_file = f"copilot_usage_data_{current_date}.csv"
    
    with open(output_file, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['team_id', 'team_name', 'day', 'total_suggestions_count', 'total_acceptances_count', 
                         'total_lines_suggested', 'total_lines_accepted', 'total_active_users', 
                         'total_chat_acceptances', 'total_chat_turns', 'total_active_chat_users',
                         'language', 'editor', 'suggestions_count', 'acceptances_count', 
                         'lines_suggested', 'lines_accepted', 'active_users'])
        
        for entry in data:
            team_id = entry['team_id']
            team_name = entry['team_name']
            if entry['data'] == "No Data":
                writer.writerow([team_id, team_name] + ["No Data"] + [0] * 16)
            else:
                for usage_entry in entry['data']:
                    if 'breakdown' in usage_entry and usage_entry['breakdown']:
                        for breakdown in usage_entry['breakdown']:
                            writer.writerow([team_id, team_name, usage_entry['day']] + 
                                            [usage_entry.get(k, 0) for k in ['total_suggestions_count', 'total_acceptances_count',
                                                                          'total_lines_suggested', 'total_lines_accepted',
                                                                          'total_active_users', 'total_chat_acceptances',
                                                                          'total_chat_turns', 'total_active_chat_users']] +
                                            [breakdown.get(k, "No Data" if k in ['language', 'editor'] else 0) for k in ['language', 'editor', 
                                                                        'suggestions_count', 'acceptances_count', 
                                                                        'lines_suggested', 'lines_accepted', 'active_users']])
                    else:
                        writer.writerow([team_id, team_name, usage_entry['day']] + 
                                        [usage_entry.get(k, 0) for k in ['total_suggestions_count', 'total_acceptances_count',
                                                                     'total_lines_suggested', 'total_lines_accepted',
                                                                     'total_active_users', 'total_chat_acceptances',
                                                                     'total_chat_turns', 'total_active_chat_users']] + 
                                        ["No Data", "No Data"] + [0] * 7)
    logging.info(f"Data written to {output_file}")

def main():
    enterprise_slug = os.getenv('ENTERPRISE_SLUG')
    token = os.getenv('GITHUB_TOKEN')
    if not enterprise_slug or not token:
        logging.error("Enterprise slug or GitHub token is missing in the .env file")
        return

    teams = fetch_teams(enterprise_slug, token)
    if not teams:
        logging.error("Failed to obtain team data")
        return

    all_data = []

    for team in teams:
        team_id = team['id']
        team_name = team['name']
        logging.info(f"Fetching data for team {team_name} with ID {team_id}")
        usage_data = fetch_copilot_usage(enterprise_slug, team_id, token)
        if usage_data:
            all_data.append({'team_id': team_id, 'team_name': team_name, 'data': usage_data})
        else:
            logging.error(f"No data to write for team {team_name} with ID {team_id}")
            all_data.append({'team_id': team_id, 'team_name': team_name, 'data': "No Data"})

    write_to_csv(all_data)

if __name__ == "__main__":
    main()
