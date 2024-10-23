# To execute this script first create a .env file and pass all the below required deatils ENTERPRISE_ID, ENTERPRISE_SLUG, GITHUB_TOKEN and then execute the script to fetch all the copilot metrics report

# ENTERPRISE_ID=your_enterprise_id_here
# ENTERPRISE_SLUG=your_enterprise_slug_here
# GITHUB_TOKEN=your_auth_token_here

import csv
import requests
import time
import logging
from datetime import datetime
from dotenv import load_dotenv
import os
import concurrent.futures

# Load environment variables from .env file
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[
    logging.FileHandler("script.log"),
    logging.StreamHandler()
])

def fetch_teams(enterprise_slug, token):
    """Fetch teams from the GitHub API with pagination handling."""
    url = f"https://api.github.com/enterprises/{enterprise_slug}/teams"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"
    }
    
    teams = []
    params = {'per_page': 100, 'page': 1}
    
    try:
        while True:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()  # Raise an error for bad status codes
            data = response.json()
            teams.extend(data)
            if 'next' in response.links:
                params['page'] += 1
            else:
                break
        team_ids = [team['id'] for team in teams]
        logging.info(f"Successfully fetched {len(team_ids)} teams")
        return team_ids
    except requests.RequestException as e:
        logging.error(f"Error fetching teams: {e}")
        return []

def fetch_copilot_usage(enterprise_id, team_id, token):
    """Fetch Copilot usage data for a given team."""
    url = f"https://api.github.com/enterprises/{enterprise_id}/team/{team_id}/copilot/usage"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"
    }
    
    retry_count = 0
    max_retries = 5
    
    while retry_count < max_retries:
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                logging.info(f"Successfully fetched data for team {team_id}")
                return response.json()
            elif response.status_code == 403 and 'X-RateLimit-Remaining' in response.headers and response.headers['X-RateLimit-Remaining'] == '0':
                reset_time = int(response.headers['X-RateLimit-Reset'])
                wait_time = max(reset_time - int(time.time()), 0) + 1
                logging.warning(f"Rate limit exceeded. Waiting for {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logging.error(f"Failed to fetch data for team {team_id}: {response.status_code} {response.text}")
        except requests.RequestException as e:
            logging.error(f"Request error for team {team_id}: {e}")
        retry_count += 1
        time.sleep(2 ** retry_count)  # Exponential backoff
    return None

def write_to_csv(team_id, data):
    """Write fetched data to a CSV file."""
    current_date = datetime.now().strftime("%Y-%m-%d")
    output_file = f"copilot_usage_data_{team_id}_{current_date}.csv"
    
    try:
        with open(output_file, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['team_id', 'day', 'total_suggestions_count', 'total_acceptances_count', 
                             'total_lines_suggested', 'total_lines_accepted', 'total_active_users', 
                             'total_chat_acceptances', 'total_chat_turns', 'total_active_chat_users',
                             'language', 'editor', 'suggestions_count', 'acceptances_count', 
                             'lines_suggested', 'lines_accepted', 'active_users'])
            
            for entry in data:
                day = entry['day']
                total_suggestions_count = entry['total_suggestions_count']
                total_acceptances_count = entry['total_acceptances_count']
                total_lines_suggested = entry['total_lines_suggested']
                total_lines_accepted = entry['total_lines_accepted']
                total_active_users = entry['total_active_users']
                total_chat_acceptances = entry['total_chat_acceptances']
                total_chat_turns = entry['total_chat_turns']
                total_active_chat_users = entry['total_active_chat_users']
                
                for breakdown in entry['breakdown']:
                    language = breakdown['language']
                    editor = breakdown['editor']
                    suggestions_count = breakdown['suggestions_count']
                    acceptances_count = breakdown['acceptances_count']
                    lines_suggested = breakdown['lines_suggested']
                    lines_accepted = breakdown['lines_accepted']
                    active_users = breakdown['active_users']
                    
                    writer.writerow([team_id, day, total_suggestions_count, total_acceptances_count, 
                                     total_lines_suggested, total_lines_accepted, total_active_users, 
                                     total_chat_acceptances, total_chat_turns, total_active_chat_users,
                                     language, editor, suggestions_count, acceptances_count, 
                                     lines_suggested, lines_accepted, active_users])
        logging.info(f"Data written to {output_file}")
    except IOError as e:
        logging.error(f"IO error while writing to file {output_file}: {e}")

def main():
    enterprise_id = os.getenv('ENTERPRISE_ID')
    enterprise_slug = os.getenv('ENTERPRISE_SLUG')
    token = os.getenv('GITHUB_TOKEN')

    if not enterprise_id or not enterprise_slug or not token:
        logging.error("Enterprise ID, Enterprise slug, or GitHub token is missing in the .env file")
        return

    team_ids = fetch_teams(enterprise_slug, token)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_team_id = {executor.submit(fetch_copilot_usage, enterprise_id, team_id, token): team_id for team_id in team_ids}
        
        for future in concurrent.futures.as_completed(future_to_team_id):
            team_id = future_to_team_id[future]
            try:
                usage_data = future.result()
                if usage_data:
                    write_to_csv(team_id, usage_data)
                else:
                    logging.error(f"No data to write for team {team_id}")
            except Exception as e:
                logging.error(f"Error processing team {team_id}: {e}")

if __name__ == "__main__":
    main()
