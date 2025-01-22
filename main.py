import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from enum import Enum as PyEnum
import time

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Database setup
Base = declarative_base()
engine = create_engine('postgresql://user:password@localhost/dbname')  # Update with your DB credentials
Session = sessionmaker(bind=engine)
session = Session()

# Define your database models
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True)
    wallet_btc = Column(String)
    wallet_eth = Column(String)
    wallet_sol = Column(String)
    wallet_usdt = Column(String)
    rating = Column(Float, default=0.0)
    review_count = Column(Integer, default=0)

class TradeOffer(Base):
    __tablename__ = 'trade_offers'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    coin = Column(String)
    price = Column(Float)
    method = Column(String)
    status = Column(String)  # e.g., 'active', 'completed', 'canceled'
    expiration = Column(Integer)  # Timestamp for expiration

class TradeStatus(PyEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELED = "canceled"

class Escrow(Base):
    __tablename__ = 'escrows'
    id = Column(Integer, primary_key=True)
    trade_offer_id = Column(Integer, ForeignKey('trade_offers.id'))
    status = Column(Enum(TradeStatus), default=TradeStatus.PENDING)

# Create tables
Base.metadata.create_all(engine)

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Welcome to the P2P Trading Bot! Please register using /register.')

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    user = User(telegram_id=user_id)
    session.add(user)
    session.commit()
    await update.message.reply_text('You have been registered! Use /add_wallet to add your wallets.')

async def add_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Please send your wallet address for BTC, ETH, SOL, USDT in the format: /add_wallet BTC your_btc_address')

async def handle_add_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        coin = context.args[0].upper()
        address = context.args[1]
        user_id = update.message.from_user.id
        user = session.query(User).filter(User.telegram_id == user_id).first()
        
        if coin == 'BTC':
            user.wallet_btc = address
        elif coin == 'ETH':
            user.wallet_eth = address
        elif coin == 'SOL':
            user.wallet_sol = address
        elif coin == 'USDT':
            user.wallet_usdt = address
        else:
            await update.message.reply_text('Invalid coin type. Please use BTC, ETH, SOL, or USDT.')
            return
        
        session.commit()
        await update.message.reply_text(f'{coin} wallet address added successfully!')
    except Exception as e:
        await update.message.reply_text(f'Error adding wallet: {str(e)}')

async def create_trade_offer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        coin, price, method, expiration = context.args
        expiration = int(expiration) + int(time.time())  # Set expiration as a timestamp
        user_id = update.message.from_user.id
        trade_offer = TradeOffer(user_id=user_id, coin=coin, price=float(price), method=method, status='active', expiration=expiration)
        session.add(trade_offer)
        session.commit()
        await update.message.reply_text('Trade offer created successfully!')
    except Exception as e:
        await update.message.reply_text(f'Error creating trade offer: {str(e)}')

async def search_trade_offers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    coin = context.args[0] if context.args else None
    offers = session.query(TradeOffer).filter(TradeOffer.coin == coin, TradeOffer.status == 'active').all()
    if offers:
        response = "Available offers:\n"
        for offer in offers:
            response += f"ID: {offer.id}, Price: {offer.price}, Method: {offer.method}, Expiration: {time.ctime(offer.expiration)}\n"
        await update.message.reply_text(response)
    else:
        await update.message.reply_text('No offers found.')

async def initiate_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        offer_id = int(context.args[0])
        offer = session.query(TradeOffer).filter(TradeOffer.id == offer_id).first()
        if offer:
            escrow = Escrow(trade_offer_id=offer_id)
            session.add(escrow)
            session.commit()
            await update.message.reply_text('Trade initiated and funds are in escrow.')
        else:
            await update.message.reply_text('Trade offer not found.')
    except Exception as e:
        await update.message.reply_text(f'Error initiating trade: {str(e)}')

async def complete_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        escrow_id = int(context.args[0])
        escrow = session.query(Escrow).filter(Escrow.id == escrow_id).first()
        if escrow:
            escrow.status = TradeStatus.COMPLETED
            session.commit()
            await update.message.reply_text('Trade completed successfully!')
        else:
            await update.message.reply_text('Escrow not found.')
    except Exception as e:
        await update.message.reply_text(f'Error completing trade: {str(e)}')

async def cancel_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        escrow_id = int(context.args[0])
        escrow = session.query(Escrow).filter(Escrow.id == escrow_id).first()
        if escrow:
            escrow.status = TradeStatus.CANCELED
            session.commit()
            await update.message.reply_text('Trade canceled successfully!')
        else:
            await update.message.reply_text('Escrow not found.')
    except Exception as e:
        await update.message.reply_text(f'Error canceling trade: {str(e)}')

def main() -> None:
    application = ApplicationBuilder().token("7671153978:AAHLBbXdZAwZ6qmb5jzyGMarx2X8bNboUX4").build()  # Replace with your bot token

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("add_wallet", add_wallet))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_wallet))
    application.add_handler(CommandHandler("create_offer", create_trade_offer))
    application.add_handler(CommandHandler("search_offers", search_trade_offers))
    application.add_handler(CommandHandler("initiate_trade", initiate_trade))
    application.add_handler(CommandHandler("complete_trade", complete_trade))
    application.add_handler(CommandHandler("cancel_trade", cancel_trade))

    application.run_polling()

if __name__ == '__main__':
    main()
