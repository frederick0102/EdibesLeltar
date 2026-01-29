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
class Location:
    """
    Helyszín/Lokáció a készletkezeléshez
    Típusok: WAREHOUSE (Raktár), CAR (Autó), VENDING (Automata)
    """
    id: int
    name: str
    location_type: str  # 'WAREHOUSE', 'CAR', 'VENDING'
    description: Optional[str] = None
    address: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None


class LocationType:
    """Helyszín típusok"""
    WAREHOUSE = 'WAREHOUSE'  # Raktár - központi tárhely
    CAR = 'CAR'              # Autó - mobil egység
    VENDING = 'VENDING'      # Automata - fogyasztási pont
    
    LABELS = {
        'WAREHOUSE': 'Raktár',
        'CAR': 'Autó',
        'VENDING': 'Automata'
    }
    
    ICONS = {
        'WAREHOUSE': '🏭',
        'CAR': '🚚',
        'VENDING': '📦'
    }
    
    @classmethod
    def get_label(cls, location_type):
        return cls.LABELS.get(location_type, location_type)
    
    @classmethod
    def get_icon(cls, location_type):
        return cls.ICONS.get(location_type, '📍')
    
    @classmethod
    def choices(cls):
        """Form select-hez"""
        return [(k, v) for k, v in cls.LABELS.items()]


@dataclass
class LocationInventory:
    """
    Készlet helyszín szerint - egy termék készlete egy adott helyszínen
    Ez a központi készletnyilvántartás: Product × Location = Quantity
    """
    id: int
    product_id: int
    location_id: int
    quantity: float = 0
    last_updated: Optional[datetime] = None
    
    # Kapcsolódó adatok (join-ból)
    product_name: Optional[str] = None
    location_name: Optional[str] = None
    location_type: Optional[str] = None


@dataclass
class InventoryMovement:
    """
    Készletmozgás - minden változás naplózása
    Helyszín-specifikus: source_location_id -> target_location_id (áthelyezésnél)
    """
    id: int
    product_id: int
    movement_type: str
    quantity_change: float
    quantity_before: float
    quantity_after: float
    location_id: Optional[int] = None          # Fő helyszín (ahol a mozgás történik)
    source_location_id: Optional[int] = None   # Forrás helyszín (áthelyezésnél)
    target_location_id: Optional[int] = None   # Cél helyszín (áthelyezésnél)
    reference_movement_id: Optional[int] = None  # Kapcsolódó mozgás (kompenzációnál)
    note: Optional[str] = None
    created_at: Optional[datetime] = None
    
    # Kapcsolódó adatok (join-ból)
    product_name: Optional[str] = None
    location_name: Optional[str] = None
    source_location_name: Optional[str] = None
    target_location_name: Optional[str] = None


# Mozgás típusok - kibővítve a multi-location támogatáshoz
class MovementType:
    # Beszerzés - külső forrásból raktárba
    STOCK_IN = 'STOCK_IN'           # Bevételezés (raktárba)
    
    # Belső áthelyezés
    TRANSFER = 'TRANSFER'           # Áthelyezés helyszínek között
    TRANSFER_OUT = 'TRANSFER_OUT'   # Kimenő áthelyezés (forrás oldal)
    TRANSFER_IN = 'TRANSFER_IN'     # Bejövő áthelyezés (cél oldal)
    
    # Fogyasztás/kiadás
    STOCK_OUT = 'STOCK_OUT'         # Kivételezés (automatából/eladás)
    CONSUMPTION = 'CONSUMPTION'     # Fogyasztás (automata feltöltésekor)
    
    # Korrekciók
    ADJUSTMENT = 'ADJUSTMENT'       # Korrekció (leltáreltérés)
    INITIAL = 'INITIAL'             # Kezdőkészlet
    RETURN = 'RETURN'               # Visszavétel
    LOSS = 'LOSS'                   # Veszteség/selejt
    
    # Kompenzáló tranzakció (visszavonás)
    REVERSAL = 'REVERSAL'           # Korábbi mozgás visszafordítása
    
    LABELS = {
        'STOCK_IN': 'Bevételezés',
        'TRANSFER': 'Áthelyezés',
        'TRANSFER_OUT': 'Kiadás (áthelyezés)',
        'TRANSFER_IN': 'Bevétel (áthelyezés)',
        'STOCK_OUT': 'Kivételezés',
        'CONSUMPTION': 'Fogyasztás',
        'ADJUSTMENT': 'Korrekció',
        'INITIAL': 'Kezdőkészlet',
        'RETURN': 'Visszavétel',
        'LOSS': 'Selejt/Veszteség',
        'REVERSAL': 'Visszavonás'
    }
    
    # Mozgás előjele (+ vagy -)
    SIGNS = {
        'STOCK_IN': 1,
        'TRANSFER_IN': 1,
        'RETURN': 1,
        'INITIAL': 1,
        'ADJUSTMENT': 0,  # Lehet + vagy -
        'STOCK_OUT': -1,
        'TRANSFER_OUT': -1,
        'CONSUMPTION': -1,
        'LOSS': -1,
        'REVERSAL': 0,  # Ellentétes az eredeti mozgással
    }
    
    @classmethod
    def get_label(cls, movement_type):
        return cls.LABELS.get(movement_type, movement_type)
    
    @classmethod
    def get_sign(cls, movement_type):
        return cls.SIGNS.get(movement_type, 0)
    
    @classmethod
    def is_inbound(cls, movement_type):
        """Növeli-e a készletet"""
        return cls.get_sign(movement_type) > 0
    
    @classmethod
    def is_outbound(cls, movement_type):
        """Csökkenti-e a készletet"""
        return cls.get_sign(movement_type) < 0
