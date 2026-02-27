#!/usr/bin/env python3
"""
Slack Lunch Analyzer
Fetches messages from the lunch channel and calculates sentiment ratings based on reactions.
"""

import os
import re
import html
import requests
from datetime import datetime, timedelta
from collections import defaultdict
from dotenv import load_dotenv
from urllib.parse import unquote
import pytz

# Load environment variables
load_dotenv()

SLACK_TOKEN = os.getenv('SLACK_TOKEN')
SLACK_COOKIE = os.getenv('SLACK_COOKIE')
CHANNEL_ID = os.getenv('CHANNEL_ID')

# URL decode cookie if it's encoded
if SLACK_COOKIE:
    SLACK_COOKIE = unquote(SLACK_COOKIE)

if not SLACK_TOKEN and not SLACK_COOKIE:
    raise ValueError("Either SLACK_TOKEN or SLACK_COOKIE must be provided in .env file")


def get_lunch_channel_id():
    """Get the channel ID for the lunch channel."""
    url = "https://slack.com/api/conversations.list"
    
    # Try multiple cookie formats
    cookie_formats = []
    if SLACK_COOKIE:
        # Format 1: As-is
        cookie_formats.append(SLACK_COOKIE)
        # Format 2: If it starts with oxd-, try with d= prefix
        if SLACK_COOKIE.startswith('oxd-'):
            cookie_formats.append(f"d={SLACK_COOKIE}")
        # Format 3: If it doesn't have d=, try adding it
        if 'd=' not in SLACK_COOKIE and not SLACK_COOKIE.startswith('oxd-'):
            cookie_formats.append(f"d={SLACK_COOKIE}")
    
    # Try each cookie format
    for cookie_format in cookie_formats:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Cookie": cookie_format
        }
        
        # Add token if available
        if SLACK_TOKEN:
            headers["Authorization"] = f"Bearer {SLACK_TOKEN}"
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('ok'):
                # Success! Find lunch channel
                for channel in data.get('channels', []):
                    if 'lunch' in channel.get('name', '').lower():
                        return channel['id']
                raise Exception("Lunch channel not found in workspace")
            elif data.get('error') != 'invalid_auth':
                # Different error, might be recoverable
                raise Exception(f"Slack API error: {data.get('error')}")
        except requests.exceptions.RequestException as e:
            # Network error, try next format
            continue
    
    # If we get here, all cookie formats failed
    # Try with just token if available
    if SLACK_TOKEN:
        headers = {
            "Authorization": f"Bearer {SLACK_TOKEN}",
            "Content-Type": "application/json"
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        if data.get('ok'):
            for channel in data.get('channels', []):
                if 'lunch' in channel.get('name', '').lower():
                    return channel['id']
    
    # All methods failed
    raise Exception(
        f"Slack API authentication failed with all methods tried.\n"
        f"Please verify:\n"
        f"  - Your SLACK_COOKIE is the full cookie string from browser (check Network tab)\n"
        f"  - The cookie hasn't expired (browser cookies expire after some time)\n"
        f"  - You copied the complete cookie value including any 'd=' prefix\n"
        f"  - If using SLACK_TOKEN, ensure it's a valid bot/user token"
    )
    
    # Find lunch channel (case-insensitive search)
    for channel in data.get('channels', []):
        if 'lunch' in channel.get('name', '').lower():
            return channel['id']
    
    raise Exception("Lunch channel not found")


def fetch_messages(channel_id, days_back=30):
    """Fetch messages from the past N days using pagination."""
    url = "https://slack.com/api/conversations.history"
    
    headers = {
        "Cookie": os.getenv("SLACK_COOKIE"),
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
        "Origin": "https://app.slack.com",
        "Referer": "https://app.slack.com/",
        "Accept": "*/*"
    }
    
    # Calculate oldest timestamp (N days ago)
    target_date = datetime.now() - timedelta(days=days_back)
    oldest_timestamp = target_date.timestamp()
    
    print(f"  Fetching messages from {target_date.strftime('%Y-%m-%d')} to today ({days_back} days back)")
    
    all_messages = []
    cursor = None
    page = 0
    
    while True:
        page += 1
        payload = {
            "token": os.getenv("SLACK_TOKEN"),
            "channel": channel_id,
            "limit": "200",  # Max per request
            "include_pin_count": "true",
            "oldest": str(oldest_timestamp)  # Always include oldest to ensure we respect the date range
        }
        
        if cursor:
            payload["cursor"] = cursor
        
        try:
            response = requests.post(url, headers=headers, data=payload, timeout=10)
            data = response.json()
            
            if not data.get('ok'):
                if page == 1:
                    print(f"❌ Error fetching messages: {data.get('error')}")
                break
            
            messages = data.get('messages', [])
            if not messages:
                break
            
            all_messages.extend(messages)
            
            # Check if we've gone back far enough
            # Note: Slack returns messages in reverse chronological order (newest first)
            # So the last message in the batch is the oldest
            if messages:
                last_message_ts = float(messages[-1].get('ts', 0))
                last_message_date = datetime.fromtimestamp(last_message_ts)
                target_date = datetime.fromtimestamp(oldest_timestamp)
                
                # Stop if we've gone past our target date
                if last_message_ts < oldest_timestamp:
                    print(f"  Reached target date: {target_date.strftime('%Y-%m-%d')}, last message: {last_message_date.strftime('%Y-%m-%d')}")
                    break
            
            # Get cursor for next page
            cursor = data.get('response_metadata', {}).get('next_cursor')
            if not cursor:
                break
            
            print(f"  Fetched page {page} ({len(messages)} messages, {len(all_messages)} total so far)...")
            
        except Exception as e:
            print(f"❌ Connection Error: {e}")
            break
    
    if page == 1 and all_messages:
        print("🔥 SUCCESS: Authenticated and fetched data!")
    
    # Debug: Show date range of fetched messages
    if all_messages:
        first_msg_ts = float(all_messages[0].get('ts', 0))
        last_msg_ts = float(all_messages[-1].get('ts', 0))
        first_date = datetime.fromtimestamp(first_msg_ts).strftime('%Y-%m-%d')
        last_date = datetime.fromtimestamp(last_msg_ts).strftime('%Y-%m-%d')
        print(f"  Date range of fetched messages: {last_date} to {first_date} ({len(all_messages)} total messages)")
    
    return all_messages


def parse_date_from_message(message):
    """Extract date from message timestamp."""
    if 'ts' in message:
        timestamp = float(message['ts'])
        date_obj = datetime.fromtimestamp(timestamp)
        return date_obj.strftime('%Y-%m-%d'), date_obj
    return None, None


def is_lunch_message(message, debug=False):
    """Detect lunch announcement messages. 
    Messages are typically sent 11am-12:15pm and may or may not explicitly mention 'lunch'."""
    text = message.get('text', '')
    text_lower = text.lower()
    
    # EXCLUSION 1: Filter out "next week" menu announcements
    if any(phrase in text_lower for phrase in ['next week', 'next week -', 'here\'s what to expect', 'anchor day lunch menu']):
        return False
    
    # EXCLUSION 2: Filter out messages that list future dates (like "Monday:", "Tuesday:", etc.)
    # These are usually weekly menu previews
    if re.search(r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday):\s*(makers|o&b|calii|pizza|pizzaiolo)', text_lower):
        return False
    
    # EXCLUSION 3: If it mentions "leftover" or "if you missed", it's a secondary post
    is_secondary = any(word in text_lower for word in ['leftover', 'missed out', 'reminder', 'mixer'])
    if is_secondary:
        return False
    
    # 1. MUST contain the @toronto tag or be from a known 'Official' pattern
    # (Note: In the API, @toronto often looks like <!subteam^SNXMQN152> or similar)
    has_target_tag = '@toronto' in text_lower or '<!subteam' in text_lower
    
    if not has_target_tag:
        return False
    
    # 2. Check message time - lunch messages are typically sent 11am-12:15pm ET
    # Slack timestamps are in UTC, so we need to convert to Eastern Time
    is_lunch_time = False
    if 'ts' in message:
        try:
            timestamp = float(message['ts'])
            # Slack timestamps are in UTC
            utc_dt = datetime.utcfromtimestamp(timestamp)
            utc_tz = pytz.UTC
            et_tz = pytz.timezone('US/Eastern')
            # Convert UTC to Eastern Time
            utc_dt = utc_tz.localize(utc_dt)
            et_dt = utc_dt.astimezone(et_tz)
            hour = et_dt.hour
            minute = et_dt.minute
            # 11:00 AM to 12:15 PM ET (11:00 to 12:15)
            if hour == 11 or (hour == 12 and minute <= 15):
                is_lunch_time = True
        except:
            pass
    
    # 3. Check for arrival phrase (including typos and variations) - OPTIONAL now
    has_arrival_phrase = any(phrase in text_lower for phrase in [
        'lunch has arrived', 'lunch is ready', 'lunch is here',
        'lunch is very',  # Handle typo "lunch is very today"
        'lunch is',  # Catch variations like "lunch is today"
        'lunch today'
    ])
    
    # 4. Check for explicit menu triggers
    has_menu_trigger = any(word in text_lower for word in [
        'menu:', 'options:', 'on the menu', 'what\'s on the menu', 
        'what\'s in the menu', 'here\'s what'
    ])
    
    # 5. Check if menu items are listed directly (items with dietary info like (GF, DF, VG, HALAL))
    has_menu_items = bool(re.search(r'\([^)]*?(?:GF|DF|VG|V|HALAL|NF)[^)]*?\)', text_lower))
    
    # 6. Check for "we have" or "today we have" followed by vendor/food
    # This is a strong signal even without "lunch" mentioned
    has_we_have_pattern = bool(re.search(r'(?:today\s+)?we have', text_lower, re.IGNORECASE))
    
    # 7. Check for "from [vendor]" pattern - e.g., "choose a bowl from Toben"
    has_from_vendor_pattern = bool(re.search(r'from\s+[A-Z][a-zA-Z\s&]+', text, re.IGNORECASE))
    
    # 8. Check for common vendor names or food-related words
    has_food_context = any(word in text_lower for word in [
        'pizza', 'bowl', 'salad', 'chicken', 'salmon', 'beef', 'pork', 
        'sandwich', 'wrap', 'taco', 'burrito', 'soup', 'rice', 'noodles',
        'pasta', 'catering', 'vendor', 'maker', 'calii', 'african', 'thai',
        'mexican', 'japanese', 'chinese', 'indian', 'italian', 'toben', 'choose'
    ])

    # The Logic: To be a lunch message, it needs:
    # - @toronto tag AND
    # - (time window 11am-12:15pm OR arrival phrase OR menu trigger OR (we have + food context) OR from vendor pattern OR menu items)
    # Lunch doesn't need to be explicitly mentioned!
    # Older messages might not have menu items, so we're more flexible
    if (is_lunch_time or has_arrival_phrase or has_menu_trigger or 
        (has_we_have_pattern and has_food_context) or has_from_vendor_pattern or has_menu_items) and not is_secondary:
        return True
        
    return False


def extract_vendor_name(message):
    """Extract catering vendor name from message text.
    Example: "today we have Calii Love" -> "Calii Love"
    Example: "we have African Palace today" -> "African Palace"
    Example: "we have East Coast inspired meals today" -> "East Coast inspired meals"
    Example: "Today we have Maker Pizza today and Pi Co" -> "Maker Pizza & Pi Co"
    Example: "we have Lala's Cantina with some delicious..." -> "Lala's Cantina"
    """
    import re
    text = html.unescape(message.get('text', ''))
    
    # First, clean up Slack link formats: <https://url|text> or <https://url>
    # Replace with just the text part or remove entirely
    text = re.sub(r'<https?://[^|>]+\|([^>]+)>', r'\1', text)  # <https://url|text> -> text
    text = re.sub(r'<https?://[^>]+>', '', text)  # <https://url> -> (remove)
    text = re.sub(r'<https?://[^>]+', '', text)  # Handle malformed links like "<https"
    
    # Pattern 1: "today we have [Vendor]:" or "today we have [Vendor]"
    # Pattern 2: "we have [Vendor] today" or "we have [Vendor]:"
    # Pattern 3: "lunch has arrived and we have [Vendor]"
    # Pattern 4: "from [Vendor]" - e.g., "choose a bowl from Toben"
    # Pattern 5: "choose [food] from [Vendor]"
    # Use more flexible pattern that allows mixed case (for "East Coast inspired meals")
    patterns = [
        r"from\s+([A-Z][a-zA-Z\s&'-]+?)(?:\s*!|\.|$)",  # "from Toben" or "from Maker Pizza"
        r"choose\s+(?:a\s+)?[^f]*?\s+from\s+([A-Z][a-zA-Z\s&'-]+?)(?:\s*!|\.|$)",  # "choose a bowl from Toben"
        r"today we have (.*?)(?:\s+today|:|\s+and\s+[A-Z]|\s+with\s+|\.|$)",  # Stop at "with" too
        r"we have (.*?)(?:\s+today|:|\s+and\s+[A-Z]|\s+with\s+|\.|$)",  # Stop at "with" too
        r"lunch has arrived.*?we have (.*?)(?::|\.)",
        r"arrived - we have (.*?) today"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            vendor = match.group(1).strip()
            # Remove emoji names (like :hearting:, :dancing-fish:)
            vendor = re.sub(r':\w+(?:-\w+)*:', '', vendor).strip()
            
            # Remove any remaining Slack link formats
            vendor = re.sub(r'<[^>]+>', '', vendor)
            
            # Handle multiple vendors separated by "and"
            # Example: "Maker Pizza today and Pi Co (Gluten Free)" -> "Maker Pizza & Pi Co"
            if ' and ' in vendor.lower():
                # Split by "and" and clean each part
                parts = re.split(r'\s+and\s+', vendor, flags=re.IGNORECASE)
                cleaned_parts = []
                for part in parts:
                    # Remove trailing "today", "with", and dietary info in parentheses
                    part = re.sub(r'\s+(today|with).*$', '', part, flags=re.IGNORECASE)
                    part = re.sub(r'\s*\([^)]*\)\s*$', '', part).strip()
                    # Remove trailing punctuation
                    part = re.sub(r'[.,;:!?]+$', '', part).strip()
                    if part and len(part) > 2 and not part.startswith('<'):
                        cleaned_parts.append(part)
                if cleaned_parts:
                    vendor = ' & '.join(cleaned_parts)
            else:
                # Clean up common trailing words - stop at "with" too
                vendor = re.sub(r'\s+(today|and|here|menu|arrived|with).*$', '', vendor, flags=re.IGNORECASE)
                # Remove dietary info in parentheses at the end
                vendor = re.sub(r'\s*\([^)]*\)\s*$', '', vendor)
                # Remove trailing punctuation
                vendor = re.sub(r'[.,;:!?]+$', '', vendor).strip()
            
            # Remove leading/trailing whitespace and check for invalid patterns
            vendor = vendor.strip()
            # Reject if it looks like a URL or link fragment
            if vendor.startswith('http') or vendor.startswith('<') or '://' in vendor:
                continue
            if len(vendor) > 2 and len(vendor) < 100:  # Increased limit for multiple vendors
                return html.unescape(re.sub(r'\*+', '', vendor).strip())
    
    # Fallback 1: Look for "from [vendor]" pattern
    from_match = re.search(r"from\s+([A-Z][a-zA-Z\s&'-]+?)(?:\s*!|\.|$)", text, re.IGNORECASE)
    if from_match:
        vendor = from_match.group(1).strip()
        vendor = re.sub(r':\w+(?:-\w+)*:', '', vendor).strip()  # Remove emojis
        vendor = re.sub(r'<[^>]+>', '', vendor)  # Remove any remaining link formats
        vendor = re.sub(r'[.,;:!?]+$', '', vendor).strip()
        # Reject if it looks like a URL or link fragment
        if not (vendor.startswith('http') or vendor.startswith('<') or '://' in vendor):
            # Limit to reasonable length (vendor names are usually short)
            if len(vendor) > 2 and len(vendor) < 50:
                return html.unescape(re.sub(r'\*+', '', vendor).strip())
    
    # Fallback 2: Look for text after "we have" until "today", ":", "with", or end of sentence
    # This handles cases like "we have East Coast inspired meals today" or "we have Lala's Cantina with..."
    fallback_match = re.search(r'we have\s+([^:\.!?]+?)(?:\s+today|\s+and\s+[A-Z]|\s+with\s+|\s*:|\.|!|\?|$)', text, re.IGNORECASE)
    if fallback_match:
        vendor = fallback_match.group(1).strip()
        vendor = re.sub(r':\w+(?:-\w+)*:', '', vendor).strip()  # Remove emojis
        vendor = re.sub(r'<[^>]+>', '', vendor)  # Remove any remaining link formats
        # Handle multiple vendors
        if ' and ' in vendor.lower():
            parts = re.split(r'\s+and\s+', vendor, flags=re.IGNORECASE)
            cleaned_parts = []
            for part in parts:
                part = re.sub(r'\s+(today|with).*$', '', part, flags=re.IGNORECASE)
                part = re.sub(r'\s*\([^)]*\)\s*$', '', part).strip()
                part = re.sub(r'[.,;:!?]+$', '', part).strip()
                if part and len(part) > 2 and not (part.startswith('http') or part.startswith('<') or '://' in part):
                    cleaned_parts.append(part)
            if cleaned_parts:
                vendor = ' & '.join(cleaned_parts)
        else:
            # Stop at "with" clause
            vendor = re.sub(r'\s+with\s+.*$', '', vendor, flags=re.IGNORECASE)
            vendor = re.sub(r'[.,;:!?]+$', '', vendor).strip()
        # Reject if it looks like a URL or link fragment
        if not (vendor.startswith('http') or vendor.startswith('<') or '://' in vendor):
            if len(vendor) > 2 and len(vendor) < 100:
                return html.unescape(re.sub(r'\*+', '', vendor).strip())
    
    return "N/A"  # Return N/A if no vendor found


def extract_menu_items(message):
    """Deep-parse menus that use 'options' and multi-line descriptions."""
    import re
    text = html.unescape(message.get('text', ''))
    
    all_items = []
    lines = text.split('\n')
    found_menu_start = False
    
    # 1. Expanded Triggers
    start_indicators = ['here\'s what', 'menu:', 'options:', 'today we have', 'in the menu', 'we have']
    stop_keywords = ['please check', 'enjoy', 'happy', '@toronto']
    # Words that signal a line is an ingredient list, not a dish name
    ingredient_keywords = ['sauce', 'seasonal', 'pickled', 'seeds', 'dressing', 'marinated', 'topped with', 'served with']

    for line in lines:
        line_clean = line.strip()
        if not line_clean: continue
        
        # 2. Detect Start
        if any(ind in line_clean.lower() for ind in start_indicators):
            found_menu_start = True
            # If this line also contains menu items (dietary info), process it too
            # Otherwise, skip to next line
            if not re.search(r'\([^)]*?(?:GF|DF|VG|V|HALAL|NF)[^)]*?\)', line_clean):
                continue
            
        if not found_menu_start: continue

        # 3. Detect Stop
        if any(stop in line_clean.lower() for stop in stop_keywords):
            break

        # 4. Handle concatenated items on same line
        # Pattern: Items often end with ")Item" where ) is followed by capital letter
        # Example: "...(DF)Lime Dressed..." or "...(GF, DF)Steamed Rice..."
        # Remove emojis and leading bullets first
        line_clean = re.sub(r':\w+(?:-\w+)*:', '', line_clean).strip()
        line_clean = re.sub(r'^[-•*]\s*', '', line_clean)
        
        if len(line_clean) < 5: continue
        
        items_in_line = []
        
        # Strategy 1: Find all positions where ) is immediately followed by a capital letter
        # This indicates a new menu item is starting
        matches = list(re.finditer(r'\)(?=[A-Z][a-z])', line_clean))
        
        if len(matches) > 0:
            # We found multiple items concatenated on this line
            # Split at each match position (after the closing paren)
            last_pos = 0
            for match in matches:
                # Extract item up to and including the closing paren
                item = line_clean[last_pos:match.start()+1].strip()  # Include the )
                if item and len(item) > 5:
                    items_in_line.append(item)
                last_pos = match.end()  # Start of next item (after the capital letter)
            
            # Add the last item (after the last split point)
            if last_pos < len(line_clean):
                last_item = line_clean[last_pos:].strip()
                if last_item and len(last_item) > 5:
                    items_in_line.append(last_item)
        else:
            # Strategy 2: Check if line has multiple items separated by commas or "and"
            # Pattern: Item (Dietary Info), Item (Dietary Info) and Item (Dietary Info)
            # Look for patterns like ") ," or ") and" after dietary info
            comma_and_matches = list(re.finditer(r'\)\s*(?:,\s*|and\s+)', line_clean, re.IGNORECASE))
            if len(comma_and_matches) > 0:
                # Split by commas/and after closing parens
                last_pos = 0
                for match in comma_and_matches:
                    # Extract item up to and including the closing paren
                    item = line_clean[last_pos:match.start()+1].strip()
                    if item and len(item) > 5:
                        items_in_line.append(item)
                    last_pos = match.end()  # Start after comma/and
                
                # Add the last item
                if last_pos < len(line_clean):
                    last_item = line_clean[last_pos:].strip()
                    if last_item and len(last_item) > 5:
                        items_in_line.append(last_item)
            else:
                # No clear split points found, treat as single item
                items_in_line = [line_clean]

        # 5. Process each item found
        for item in items_in_line:
            item = item.strip()
            if len(item) < 5: continue

            # Filter out Ingredient Lines
            # If the line has more than 2 ingredient keywords, it's a description, skip it.
            ingredient_count = sum(1 for word in ingredient_keywords if word in item.lower())
            if ingredient_count >= 2 and (len(item) > 60 or item.count(',') > 3):
                continue

            # Extract the dish name - stop at dietary bracket or take first meaningful part
            display_name = item
            
            # Look for dietary info in parentheses (GF, DF, VG, etc.)
            bracket_match = re.search(r'\([^)]*?(?:GF|DF|VG|V|HALAL|NF)[^)]*?\)', item, re.IGNORECASE)
            if bracket_match:
                # Extract up to and including the dietary bracket
                display_name = item[:bracket_match.end()].strip()
            else:
                # No dietary bracket found - take first meaningful part
                if item.count(',') > 3:
                    # Likely has many ingredients, take first part
                    commas = [i for i, char in enumerate(item) if char == ',']
                    if len(commas) >= 2 and commas[1] < 60:
                        display_name = item[:commas[1]].strip()
                    elif len(commas) >= 1 and commas[0] < 50:
                        display_name = item[:commas[0]].strip()
                    else:
                        display_name = item[:60].strip()
                elif len(item) > 80:
                    display_name = item[:60].strip()
            
            # Clean up the display name
            display_name = display_name.strip()
            
            if len(display_name) > 3 and display_name not in all_items:
                all_items.append(display_name)

    # 6. Build Output
    if all_items:
        preview = ", ".join(all_items[:3])
        if len(all_items) > 3: preview += f" (+{len(all_items)-3})"
        return f"Items: {preview}"
        
    return "Menu details in post"

def fetch_thread_replies(channel_id, thread_ts):
    """Fetch replies in a thread."""
    url = "https://slack.com/api/conversations.replies"
    
    headers = {
        "Cookie": os.getenv("SLACK_COOKIE"),
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
        "Origin": "https://app.slack.com",
        "Referer": "https://app.slack.com/",
        "Accept": "*/*"
    }
    
    payload = {
        "token": os.getenv("SLACK_TOKEN"),
        "channel": channel_id,
        "ts": thread_ts,
        "limit": "100"
    }
    
    try:
        response = requests.post(url, headers=headers, data=payload, timeout=10)
        data = response.json()
        if data.get('ok'):
            # Return all replies except the first one (which is the parent message)
            replies = data.get('messages', [])
            return replies[1:] if len(replies) > 1 else []
    except:
        pass
    
    return []


def analyze_sentiment(text):
    """Simple sentiment analysis - look for positive food-related phrases and emojis."""
    import re
    text_lower = text.lower()
    
    positive_phrases = [
        'so good', 'really good', 'amazing', 'delicious', 'love', 'loved',
        'excellent', 'great', 'fantastic', 'best', 'favorite', 'yummy',
        'tasty', 'perfect', 'incredible', 'wow', 'fire', '🔥', 'this',
        'yes', 'agreed', 'same', 'facts', 'truth'
    ]
    
    negative_phrases = [
        'bad', 'terrible', 'awful', 'disgusting', 'hate', 'worst',
        'disappointed', 'not good', 'meh', 'bland'
    ]
    
    # Positive emoji names (like :chef_kiss:, :fire:, :heart_eyes:, etc.)
    positive_emoji_patterns = [
        'chef', 'kiss', 'fire', 'heart', 'star', 'drool', 'yum', '100',
        'exploding', 'party', 'clap', 'raised_hands', 'thumbsup', 'thumbs_up',
        'muscle', 'ok_hand', 'check', 'white_check_mark', 'checkmark'
    ]
    
    # Negative emoji names
    negative_emoji_patterns = [
        'thumbsdown', 'thumbs_down', 'x', 'cross', 'disappointed', 'sad'
    ]
    
    score = 0
    
    # Check for positive phrases
    for phrase in positive_phrases:
        if phrase in text_lower:
            score += 2
    
    # Check for negative phrases
    for phrase in negative_phrases:
        if phrase in text_lower:
            score -= 2
    
    # Check for emoji names in text (format: :emoji_name:)
    emoji_matches = re.findall(r':(\w+(?:[-_]\w+)*):', text_lower)
    for emoji_name in emoji_matches:
        # Check if it's a positive emoji
        if any(pattern in emoji_name for pattern in positive_emoji_patterns):
            score += 2
        # Check if it's a negative emoji
        elif any(pattern in emoji_name for pattern in negative_emoji_patterns):
            score -= 2
    
    return score


def calculate_sentiment_rating(message, channel_id, thread_replies=None):
    """Calculate sentiment rating based on emoji meaning, thread replies, and sentiment."""
    total_score = 0
    
    # Check if message mentions rescheduling/cancellation - reduce weight of reactions
    # People might be reacting to the cancellation news, not the actual lunch
    text = message.get('text', '').lower()
    is_rescheduling = any(word in text for word in [
        'rescheduled', 'reschedule', 'cancelled', 'canceled', 'cancellation',
        'change in plans', 'quick change', 'originally planning', 'postponed'
    ])
    
    # Score based on emoji meaning (not type)
    reactions = message.get('reactions', [])
    for reaction in reactions:
        name = reaction.get('name', '').lower()
        count = reaction.get('count', 0)
        
        # If message mentions rescheduling, reduce reaction weight by 50%
        # Reactions might be about the cancellation, not the actual lunch
        weight_multiplier = 0.5 if is_rescheduling else 1.0
        
        # Positive/enthusiastic emojis (heart eyes, star eyes, etc.)
        if any(x in name for x in ['heart_eyes', 'star_struck', 'drooling', 'yum', 'fire', '100', 'exploding_head']):
            total_score += int(count * 3 * weight_multiplier)
        # Positive emojis (hearts, stars, thumbs up)
        elif any(x in name for x in ['heart', 'star', 'thumbsup', '+1', 'clap', 'party', 'raised_hands']):
            total_score += int(count * 2 * weight_multiplier)
        # Neutral/other reactions
        else:
            total_score += int(count * 1 * weight_multiplier)
    
    # Add score from thread replies
    # If message mentions rescheduling, reduce weight of replies too
    # (people might be commenting on the cancellation, not the actual lunch)
    reply_weight_multiplier = 0.5 if is_rescheduling else 1.0
    
    if thread_replies:
        total_score += int(len(thread_replies) * 2 * reply_weight_multiplier)  # Each reply adds 2 points
        
        # Analyze sentiment in replies
        for reply in thread_replies:
            reply_text = reply.get('text', '')
            sentiment_score = analyze_sentiment(reply_text)
            total_score += int(sentiment_score * reply_weight_multiplier)
            
            # Determine if this is a positive comment (for weighting reactions)
            is_positive_comment = sentiment_score > 0
            
            # Count reactions on replies - these represent agreement
            # If the comment is positive, reactions = people agreeing, so weight them higher
            reply_reactions = reply.get('reactions', [])
            for reaction in reply_reactions:
                name = reaction.get('name', '').lower()
                count = reaction.get('count', 0)
                
                # Agreement reactions (checkmarks, thumbs up, "this", etc.)
                agreement_emojis = ['check', 'white_check_mark', 'checkmark', 'thumbsup', '+1', 'this']
                is_agreement = any(x in name for x in agreement_emojis)
                
                if is_positive_comment:
                    # On positive comments, agreement reactions are especially valuable
                    if is_agreement:
                        total_score += int(count * 3 * reply_weight_multiplier)  # Higher weight for agreement on positive comments
                    elif any(x in name for x in ['heart_eyes', 'star_struck', 'drooling', 'yum', 'fire', 'chef', 'kiss']):
                        total_score += int(count * 3 * reply_weight_multiplier)  # Enthusiastic agreement
                    elif any(x in name for x in ['heart', 'star', 'clap', 'party', 'raised_hands']):
                        total_score += int(count * 2 * reply_weight_multiplier)  # Positive agreement
                    else:
                        total_score += int(count * 1 * reply_weight_multiplier)  # Any reaction on positive comment = agreement
                else:
                    # Regular reactions on non-positive comments
                    if any(x in name for x in ['heart_eyes', 'star_struck', 'drooling', 'yum', 'fire']):
                        total_score += int(count * 2 * reply_weight_multiplier)
                    elif any(x in name for x in ['heart', 'star', 'thumbsup', '+1', 'check']):
                        total_score += int(count * 1 * reply_weight_multiplier)
                    else:
                        total_score += int(count * 1 * reply_weight_multiplier)
    
    return total_score


def print_table(headers, rows):
    """Print a formatted table without external dependencies."""
    # Calculate column widths
    col_widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))
    
    # Add padding
    col_widths = [w + 2 for w in col_widths]
    
    # Print header
    header_row = " | ".join(str(h).ljust(col_widths[i]) for i, h in enumerate(headers))
    print(header_row)
    print("-" * len(header_row))
    
    # Print rows
    for row in rows:
        row_str = " | ".join(str(cell).ljust(col_widths[i]) if i < len(col_widths) else str(cell) 
                            for i, cell in enumerate(row))
        print(row_str)


def analyze_lunches(days_back=30):
    """Main function to analyze lunch messages.
    
    Args:
        days_back: Number of days to look back for lunch messages (default: 30)
    """
    print(f"🍽️  Fetching lunch channel data (past {days_back} days)...")
    
    # Get channel ID - use from .env if provided, otherwise find it
    if CHANNEL_ID:
        channel_id = CHANNEL_ID
        print(f"✓ Using channel ID from .env: {channel_id}")
    else:
        channel_id = get_lunch_channel_id()
        print(f"✓ Found lunch channel: {channel_id}")
    
    # Fetch messages from specified time period
    messages = fetch_messages(channel_id, days_back=days_back)
    print(f"✓ Fetched {len(messages)} total messages")
    
    # Filter and process lunch messages
    lunch_data = []
    lunch_by_date = {}  # Track best lunch message per date (prefer messages around noon)
    
    # Debug counters
    messages_with_lunch = 0
    passed_lunch_filter = 0
    passed_weekday_filter = 0
    passed_vendor_filter = 0
    skipped_duplicate_date = 0
    
    def get_message_priority_score(message, date_obj):
        """Calculate a priority score for lunch messages.
        Higher score = better lunch message. Considers both time and message quality.
        """
        hour = date_obj.hour
        minute = date_obj.minute
        time_minutes = hour * 60 + minute
        
        # Target: 12:00 PM (noon) = 12 * 60 = 720 minutes
        target_minutes = 12 * 60
        
        # Base time score
        if 660 <= time_minutes <= 780:  # 11:00 - 13:00
            distance_from_noon = abs(time_minutes - target_minutes)
            time_score = 1000 - distance_from_noon  # Max score ~1000
        else:
            distance_from_noon = abs(time_minutes - target_minutes)
            time_score = 500 - distance_from_noon  # Max score ~500 for non-lunch-time messages
        
        # Quality bonuses for better lunch messages
        text = message.get('text', '').lower()
        quality_bonus = 0
        
        # Bonus for explicit "lunch has arrived" phrase (strongest signal)
        if 'lunch has arrived' in text:
            quality_bonus += 500
        
        # Bonus for menu items with dietary info (complete menu)
        if re.search(r'\([^)]*?(?:GF|DF|VG|V|HALAL|NF)[^)]*?\)', text):
            quality_bonus += 300
        
        # Bonus for "here's what's on the menu" (explicit menu trigger)
        if any(phrase in text for phrase in ["here's what", "what's on the menu", "what's in the menu"]):
            quality_bonus += 200
        
        # Bonus for vendor name patterns (complete lunch info)
        # Check for common vendor patterns without full extraction
        if re.search(r"(?:we have|today we have|from)\s+[A-Z][a-zA-Z\s&'-]+", text, re.IGNORECASE):
            quality_bonus += 100
        
        return time_score + quality_bonus
    
    for message in messages:
        text = message.get('text', '').lower()
        
        # Count messages with "lunch" keyword
        if 'lunch' in text:
            messages_with_lunch += 1
        
        # Only process lunch messages (not leftover call-outs, etc.)
        if not is_lunch_message(message):
            continue
        
        passed_lunch_filter += 1
        
        date, date_obj = parse_date_from_message(message)
        if not date or not date_obj:
            continue
        
        # Only include Mon-Fri (weekdays)
        if date_obj.weekday() >= 5:  # Saturday = 5, Sunday = 6
            continue
        
        passed_weekday_filter += 1
        
        # Only one lunch per day - prefer messages with better quality and closer to noon
        priority_score = get_message_priority_score(message, date_obj)
        
        if date in lunch_by_date:
            # We already have a lunch for this date - compare priority scores
            existing_score = lunch_by_date[date]['priority_score']
            if priority_score > existing_score:
                # This message has higher priority (better quality or closer to noon), replace the existing one
                skipped_duplicate_date += 1
                lunch_by_date[date] = {
                    'message': message,
                    'date': date,
                    'date_obj': date_obj,
                    'priority_score': priority_score
                }
            else:
                # Existing message is better, skip this one
                skipped_duplicate_date += 1
        else:
            # First lunch message for this date
            lunch_by_date[date] = {
                'message': message,
                'date': date,
                'date_obj': date_obj,
                'priority_score': priority_score
            }
    
    # Process the selected lunch messages (one per date, preferring noon-time messages)
    for date, lunch_info in lunch_by_date.items():
        message = lunch_info['message']
        date_obj = lunch_info['date_obj']
        
        vendor = extract_vendor_name(message)
        
        # Vendor will be "N/A" if not found, or the actual vendor name if extracted
        # (including "O&B" if it's mentioned in the message)
        
        # Always count as passed - we don't filter out messages without vendor names
        passed_vendor_filter += 1
        
        # Extract menu items
        menu = extract_menu_items(message)
        
        # Fetch thread replies if this message has a thread
        thread_replies = []
        if message.get('thread_ts'):
            thread_replies = fetch_thread_replies(channel_id, message.get('thread_ts'))
        
        # Calculate sentiment rating with thread replies
        sentiment_rating = calculate_sentiment_rating(message, channel_id, thread_replies)
        
        lunch_data.append({
            'date': date,
            'vendor': vendor,
            'menu': html.unescape(menu) if isinstance(menu, str) else menu,
            'sentiment_rating': sentiment_rating,
            'message_text': html.unescape(message.get('text', ''))[:150],  # First 150 chars
            'reply_count': len(thread_replies)
        })
    
    # Print debug info
    print(f"\n📊 Debug Info:")
    print(f"  Messages with 'lunch' keyword: {messages_with_lunch}")
    print(f"  Passed lunch message filter: {passed_lunch_filter}")
    print(f"  Passed weekday filter (Mon-Fri): {passed_weekday_filter}")
    print(f"  Passed vendor extraction: {passed_vendor_filter}")
    print(f"  Skipped duplicate dates: {skipped_duplicate_date}")
    print(f"  Final unique lunches: {len(lunch_data)}")
    
    if not lunch_data:
        print("\n❌ No lunch data found in messages.")
        print("   This might mean:")
        print("   - Messages don't match the expected format")
        print("   - Vendor names aren't being extracted correctly")
        print("   - Messages are being filtered out too strictly")
        return None
    
    print(f"\n✓ Found {len(lunch_data)} unique lunch days (Mon-Fri only)")
    
    # Sort by sentiment rating (highest first)
    lunch_data_sorted = sorted(lunch_data, key=lambda x: x['sentiment_rating'], reverse=True)
    
    # Add rank and weekday to each lunch item
    for i, lunch in enumerate(lunch_data_sorted, 1):
        date_obj = datetime.strptime(lunch['date'], '%Y-%m-%d')
        lunch['rank'] = i
        lunch['weekday'] = date_obj.strftime('%a')
        lunch['date_obj'] = date_obj
    
    # Print ALL lunches table sorted by sentiment rating
    print("\n" + "="*100)
    print("📋 ALL LUNCHES RETRIEVED (sorted by sentiment rating, highest first)")
    print("="*100)
    
    all_table = []
    for lunch in lunch_data_sorted:
        menu_preview = lunch['menu'][:50] + "..." if len(lunch['menu']) > 50 else lunch['menu']
        reply_info = f"{lunch['reply_count']} replies" if lunch['reply_count'] > 0 else "no replies"
        all_table.append([
            lunch['rank'],
            lunch['date'],
            lunch['weekday'],
            lunch['vendor'],
            lunch['sentiment_rating'],
            reply_info,
            menu_preview
        ])
    
    print_table(['Rank', 'Date', 'Day', 'Vendor', 'Sentiment Rating', 'Replies', 'Menu'], all_table)
    
    print("\n" + "="*100)
    print(f"📊 Total lunches analyzed: {len(lunch_data)}")
    print(f"📈 Average sentiment rating: {sum(l['sentiment_rating'] for l in lunch_data) / len(lunch_data):.2f}")
    print("="*100)
    
    return lunch_data_sorted


if __name__ == "__main__":
    try:
        analyze_lunches()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
