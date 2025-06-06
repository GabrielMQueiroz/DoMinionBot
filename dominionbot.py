# main_bot.py
import discord
from discord.ext import commands
import os
import re
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

# --- Configuration ---
# Load environment variables from .env file
load_dotenv('C:/Users/gabri/Desktop/Prog/Cred/bot.env')
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
GOOGLE_DOC_ID = os.getenv('GOOGLE_DOC_ID') # The ID of your Google Doc file
PATH_TO_GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON_PATH', 'service_account.json') # Path to your service account key file

# Google API Scopes
SCOPES = ['https://www.googleapis.com/auth/documents.readonly', 'https://www.googleapis.com/auth/drive.readonly']

# Bot Setup
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# --- Google Docs Helper Functions ---

def get_google_docs_service():
    """Authenticates with Google Docs API using a service account and returns the service object."""
    print(f"Attempting to load service account credentials from: {PATH_TO_GOOGLE_SERVICE_ACCOUNT_JSON}")
    try:
        creds = service_account.Credentials.from_service_account_file(
            PATH_TO_GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES)
        service = build('docs', 'v1', credentials=creds)
        return service
    except FileNotFoundError:
        print(f"Error: Service account key file not found at '{PATH_TO_GOOGLE_SERVICE_ACCOUNT_JSON}'.")
        print("Please ensure the GOOGLE_SERVICE_ACCOUNT_JSON_PATH environment variable is set correctly or the file is in the default location.")
        return None
    except Exception as e:
        print(f"An error occurred during Google authentication: {e}")
        return None

def read_google_doc_content(service, document_id):
    """Reads the content of a Google Doc."""
    if not service:
        return None
    try:
        document = service.documents().get(documentId=document_id, fields='body(content(paragraph(elements(textRun(content,textStyle)))))').execute()
        doc_content = document.get('body').get('content')
        
        text = ""
        if doc_content: # Check if doc_content is not None
            for element in doc_content:
                if 'paragraph' in element:
                    para_elements = element.get('paragraph').get('elements')
                    if para_elements: # Check if para_elements is not None
                        for para_element in para_elements:
                            if 'textRun' in para_element:
                                text_run_content = para_element.get('textRun').get('content')
                                if text_run_content: # Check if text_run_content is not None
                                    text += text_run_content
        return text
    except Exception as e:
        print(f"An error occurred while reading the Google Doc: {e}")
        return None

def parse_character_stats(doc_text_content, discord_mention_tag):
    """
    Parses the document content to find stats for a specific Discord user.
    Format:
    Player: @Username#1234
    Character Name: CharName
    Stat1: Value1
    ...
    ---
    """
    if not doc_text_content:
        return None

    target_player_line = f"Player: {discord_mention_tag}"
    print(f"Searching for player line: '{target_player_line}' in document.")

    character_blocks = doc_text_content.split('X_X_X')
    stats = {}
    found_player = False

    for block in character_blocks:
        block = block.strip()
        lines = block.split('\n')
        if not lines or not lines[0].strip(): # Ensure there's a first line
            continue
        
        # Normalize and compare the player line
        # Handles potential extra spaces or case differences if any, though exact match is better
        current_player_line = lines[0].strip()
        print(f"Checking block starting with: '{current_player_line}'") # Debug

        if current_player_line == target_player_line:
            found_player = True
            stats['Player'] = discord_mention_tag 
            for line in lines[1:]:
                line = line.strip()
                if ':' in line:
                    key, value = line.split(':', 1)
                    stats[key.strip()] = value.strip()
            print(f"Found and parsed stats for {discord_mention_tag}: {stats}") # Debug
            break 
            
    if not found_player:
        print(f"Player block not found for {discord_mention_tag}")
        return None
        
    return stats

# --- Discord Bot Events and Commands ---

@bot.event
async def on_ready():
    """Event that runs when the bot is connected and ready."""
    print(f'{bot.user.name} has connected to Discord!')
    print(f"Operating in {len(bot.guilds)} guild(s).")
    google_service = get_google_docs_service()
    if google_service:
        print("Successfully authenticated with Google APIs.")
    else:
        print("Failed to authenticate with Google APIs. Check logs.")

@bot.command(name='charstats', help='Fetches character stats for a mentioned user. Usage: !charstats @Username')
async def charstats(ctx, member: discord.Member = None):
    """Command to fetch and display character stats."""
    if member is None:
        await ctx.send("Please mention a user to get their character stats. Usage: `!charstats @Username`")
        return

    discord_user_tag = f"@{member.name}#{member.discriminator}"
    await ctx.send(f"Fetching stats for {discord_user_tag} from Google Docs...")

    gdocs_service = get_google_docs_service()
    if not gdocs_service:
        await ctx.send("Error: Could not connect to Google Services. Check bot logs.")
        return

    doc_content_text = read_google_doc_content(gdocs_service, GOOGLE_DOC_ID)
    if not doc_content_text:
        await ctx.send(f"Error: Could not read the Google Doc (ID: {GOOGLE_DOC_ID}). Make sure it's shared correctly, the ID is valid, and the document is not empty.")
        return
    
    stats = parse_character_stats(doc_content_text, discord_user_tag)

    if stats:
        MAX_EMBED_FIELDS = 24 # Max fields, leaving one for a potential "truncated" message
        
        embed = discord.Embed(
            title=f"Character Stats for {stats.get('Character Name', discord_user_tag)}",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=member.display_avatar.url) # Optional

        if 'Character Name' in stats:
            embed.description = f"**Character:** {stats['Character Name']}"
        else:
            embed.description = "Character name not found in stats."

        # Prepare fields, excluding Player and Character Name which are handled
        fields_to_add = []
        for key, value in stats.items():
            if key.lower() not in ['player', 'character name']:
                fields_to_add.append((key, value))
        
        truncated = False
        if len(fields_to_add) > MAX_EMBED_FIELDS:
            fields_to_add = fields_to_add[:MAX_EMBED_FIELDS]
            truncated = True

        for key, value in fields_to_add:
            embed.add_field(name=key, value=value, inline=True)
        
        if truncated:
            embed.set_footer(text=f"Note: Some stats were truncated as they exceed Discord's display limit ({MAX_EMBED_FIELDS} fields).")

        await ctx.send(embed=embed)
    else:
        await ctx.send(f"Could not find character stats for {discord_user_tag} in the document. Ensure the player tag (e.g., Player: @Username#1234) and format are correct in the Google Doc.")

@charstats.error
async def charstats_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("You need to mention a user! Usage: `!charstats @Username`")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send(f"Could not find the user: {error.argument}. Please make sure you've entered a valid @mention or UserID.")
    else:
        await ctx.send("An unexpected error occurred. Please check the bot logs.")
        print(f"Error in charstats command: {error}")


# --- Main Execution ---
if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        print("Error: DISCORD_BOT_TOKEN environment variable not set.")
    elif not GOOGLE_DOC_ID:
        print("Error: GOOGLE_DOC_ID environment variable not set.")
    elif not os.path.exists(PATH_TO_GOOGLE_SERVICE_ACCOUNT_JSON) and PATH_TO_GOOGLE_SERVICE_ACCOUNT_JSON == 'service_account.json':
         print(f"Warning: Default service account file '{PATH_TO_GOOGLE_SERVICE_ACCOUNT_JSON}' not found. Ensure GOOGLE_SERVICE_ACCOUNT_JSON_PATH is set if using a different path/name.")
    else:
        try:
            bot.run(DISCORD_BOT_TOKEN)
        except discord.errors.LoginFailure:
            print("Error: Improper token has been passed. Make sure your DISCORD_BOT_TOKEN is correct.")
        except Exception as e:
            print(f"An error occurred while running the bot: {e}")