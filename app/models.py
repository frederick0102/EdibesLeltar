"""
Adatmodell osztályok a leltárkezelőhöz
"""
from flask_login import UserMixin
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


class User(UserMixin):
    """Egyszerű felhasználó osztály a bejelentkezéshez"""
    def __init__(self, id):
        self.id = id
    
    @staticmethod
    def get(user_id):
        if user_id == 'admin':
            return User('admin')
        return None


@dataclass
class Category:
    """Termékkategória"""
    id: int
    name: str
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None


@dataclass
class Unit:
    """Mennyiségi egység"""
    id: int
    name: str
    abbreviation: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None


@dataclass
class Product:
    """Termék törzsadat"""
    id: int
    name: str
    category_id: Optional[int] = None
    unit_id: Optional[int] = None
    barcode: Optional[str] = None
    description: Optional[str] = None
    min_stock_level: float = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    
    # Kapcsolódó adatok (join-ból)
    category_name: Optional[str] = None
    unit_name: Optional[str] = None
    unit_abbreviation: Optional[str] = None
    current_quantity: float = 0


@dataclass
class InventoryMovement:
    """Készletmozgás"""
    id: int
    product_id: int
    movement_type: str
    quantity_change: float
    quantity_before: float
    quantity_after: float
    note: Optional[str] = None
    created_at: Optional[datetime] = None
    
    # Kapcsolódó adatok (join-ból)
    product_name: Optional[str] = None


# Mozgás típusok
class MovementType:
    STOCK_IN = 'STOCK_IN'       # Bevételezés
    STOCK_OUT = 'STOCK_OUT'     # Kivételezés (automatába töltés)
    ADJUSTMENT = 'ADJUSTMENT'    # Korrekció
    INITIAL = 'INITIAL'         # Kezdőkészlet
    RETURN = 'RETURN'           # Visszavétel
    LOSS = 'LOSS'               # Veszteség/selejt
    
    LABELS = {
        'STOCK_IN': 'Bevételezés',
        'STOCK_OUT': 'Kivételezés',
        'ADJUSTMENT': 'Korrekció',
        'INITIAL': 'Kezdőkészlet',
        'RETURN': 'Visszavétel',
        'LOSS': 'Selejt/Veszteség'
    }
    
    @classmethod
    def get_label(cls, movement_type):
        return cls.LABELS.get(movement_type, movement_type)
