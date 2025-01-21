import base58
import requests
import time
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackContext, filters
from solana.rpc.api import Client
from solana.keypair import Keypair
from solana.publickey import PublicKey
from solana.transaction import Transaction
from solana.token.instructions import transfer as token_transfer
from solana.token.constants import TOKEN_PROGRAM_ID
import asyncio

# ============ CONFIGURATION ============
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # Store your bot token in an environment variable
OWNER_ID = os.getenv("TELEGRAM_OWNER_ID")  # Store your Telegram ID in an environment variable
RPC_URL = "https://api.mainnet-beta.solana.com"
solana_client = Client(RPC_URL)

# === YOUR WALLET ===
YOUR_PRIVATE_KEY = os.getenv("SOLANA_PRIVATE_KEY")  # Store your private key in an environment variable
your_wallet = Keypair.from_secret_key(base58.b58decode(YOUR_PRIVATE_KEY))

# === MONITORED WALLETS ===
wallets_to_monitor = [
    "4WAfwi1V6jUmFasSgMK3roUo6y9mHXxcUV75tVU9NtnQ",
    "CQvwRHaxNUScPrE3VTJsbw8LNRudaKS52LZb4r4zcuuB"
]

is_copy_trading_active = False

# === COMMAND HANDLERS ===

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "🔥 Welcome to Solana Copy Trading Bot! Developed by Stupidmoni-dev. "
        "Use /help to get the list of commands. I will assist you in creating and importing wallets."
    )
    await fetch_and_show_solana_price(update)

async def fetch_and_show_solana_price(update: Update):
    sol_price = await get_solana_price()
    await update.message.reply_text(f"💰 Current Solana Price: {sol_price} USD")

async def get_solana_price():
    response = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd")
    data = response.json()
    return data["solana"]["usd"]

async def generate_wallet(update: Update, context: CallbackContext):
    keypair = Keypair.generate()
    public_key = keypair.public_key
    private_key = base58.b58encode(keypair.secret_key).decode()

    await update.message.reply_text(
        f"✅ New wallet generated! Here's your private key and public key:\n\n"
        f"Private Key: {private_key}\nPublic Key: {public_key}"
    )

async def import_wallet(update: Update, context: CallbackContext):
    await update.message.reply_text("🔑 Please provide your Solana private key to import your wallet.")

async def handle_imported_wallet(update: Update, context: CallbackContext):
    private_key = update.message.text.strip()
    
    try:
        keypair = Keypair.from_secret_key(base58.b58decode(private_key))
        public_key = keypair.public_key
        balance = await get_balance(public_key)

        await update.message.reply_text(
            f"✅ Wallet imported successfully! Public Key: {public_key}\nBalance: {balance} SOL"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error importing wallet: Invalid private key or other issue.")

async def get_balance(public_key: PublicKey):
    balance_response = await solana_client.get_balance(public_key)
    if 'result' in balance_response:
        return balance_response['result']['value'] / 10**9  # Convert lamports to SOL
    else:
        return 0  # Return 0 if there's no balance or error

async def start_copy(update: Update, context: CallbackContext):
    global is_copy_trading_active
    is_copy_trading_active = True
    await update.message.reply_text("✅ Copy Trading Started!")

async def stop_copy(update: Update, context: CallbackContext):
    global is_copy_trading_active
    is_copy_trading_active = False
    await update.message.reply_text("🛑 Copy Trading Stopped!")

async def help_command(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "🛠 Available Commands:\n"
        "/start - Start the bot\n"
        "/generate_wallet - Generate a new wallet\n"
        "/import_wallet - Import an existing wallet\n"
        "/start_copy - Start copy trading\n"
        "/stop_copy - Stop copy trading\n"
        "/help - Show this help message"
    )

# === MONITOR & COPY TRADES ===
async def monitor_and_copy_trades(context: CallbackContext):
    global is_copy_trading_active
    if not is_copy_trading_active:
        return

    for wallet in wallets_to_monitor:
        transactions = await fetch_recent_transactions(wallet)

        for tx in transactions:
            signature = tx.get("signature")
            tx_details = await solana_client.get_transaction(signature)
            if not tx_details.get("result"):
                continue

            instructions = tx_details["result"]["transaction"]["message"]["instructions"]
            for instruction in instructions:
                if "program" in instruction and instruction["program"] == "spl-token":
                    token_address = instruction["parsed"]["info"]["mint"]
                    amount = instruction["parsed"]["info"]["amount"]
                    action = "buy" if instruction["parsed"]["type"] == "transfer" else "sell"

                    await execute_trade(action, token_address, amount)
                    await context.bot.send_message(OWNER_ID, f"🔄 Copied Trade: {action.upper()} {amount} of {token_address}")

async def fetch_recent_transactions(wallet_address):
    pub_key = PublicKey(wallet_address)
    transactions = await solana_client.get_signatures_for_address(pub_key, limit=5)
    return transactions.get("result", [])

async def execute_trade(action, token_address, amount):
    print(f"[Trade] {action.upper()} {amount} of {token_address} using {your_wallet.public_key}")
    
    destination_address = PublicKey("YourReceiverPublicKey")  # Replace with a valid address

    transfer_instruction = token_transfer(
        TOKEN_PROGRAM_ID,
        your_wallet.public_key,
        destination_address,
        amount,
        TOKEN_PROGRAM_ID
    )

    transaction = Transaction().add(transfer_instruction)
    try:
        response = await solana_client.send_transaction(transaction, your_wallet)
        if response.get("result"):
            print(f"Transaction successful: {response['result']}")
        else:
            print(f"Transaction failed: {response.get('error', 'Unknown error')}")
    except Exception as e:
        print(f"Error executing trade: {str(e)}")

async def rate_limited_request(func, *args, **kwargs):
    """Rate-limit API requests by introducing a delay between requests."""
    await asyncio.sleep(1)  # Introduce a 1-second delay between requests to avoid overloading
    return await func(*args, **kwargs)

# === TELEGRAM BOT SETUP ===
async def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers for commands and messages
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("generate_wallet", generate_wallet))
    application.add_handler(CommandHandler("import_wallet", import_wallet))
    application.add_handler(CommandHandler("start_copy", start_copy))
    application.add_handler(CommandHandler("stop_copy", stop_copy))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_imported_wallet))

    # Run trading bot every 10 seconds
    job_queue = application.job_queue
    job_queue.run_repeating(monitor_and_copy_trades, interval=10, first=10)

    await application.run_polling()
    print("🚀 Telegram Bot is Running!")

if __name__ == "__main__":
    asyncio.run(main())  # Ensure the coroutine is properly awaited
