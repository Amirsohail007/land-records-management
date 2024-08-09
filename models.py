from sqlalchemy import create_engine, Column, String, Integer, DateTime, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func


# Base class
Base = declarative_base()


class LandRecord(Base):
    __tablename__ = 'land_records'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    district_name = Column(String, nullable=False)
    district_code = Column(String, nullable=False)
    tehsil_name = Column(String, nullable=False)
    tehsil_code = Column(String, nullable=False)
    villege_name = Column(String, nullable=False)
    villege_code = Column(String, nullable=False)
    jamabandi_year = Column(String, nullable=False)
    khewat_no = Column(String, nullable=False)
    khatoni_no = Column(String, nullable=False)
    khasra_code = Column(String, nullable=False)
    khasra_no = Column(String, nullable=False)
    
    nakal_villege = Column(String, nullable=False)
    nakal_hadbast = Column(String, nullable=False)
    nakal_tehsil = Column(String, nullable=False)
    nakal_district = Column(String, nullable=False)
    nakal_year = Column(String, nullable=False)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Creating composite index to support efficient searching
    __table_args__ = (
        Index('idx_district_tehsil_village', 'district_name', 'tehsil_name', 'villege_name'),
    )

    def to_dict(self):
        """
        Convert the LandRecord instance to a dictionary.
        """
        def format_datetime(dt):
            if dt:
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            return None
        return {
            'id': self.id,
            'district_name': self.district_name,
            'district_code': self.district_code,
            'tehsil_name': self.tehsil_name,
            'tehsil_code': self.tehsil_code,
            'villege_name': self.villege_name,
            'villege_code': self.villege_code,
            'jamabandi_year': self.jamabandi_year,
            'khewat_no': self.khewat_no,
            'khatoni_no': self.khatoni_no,
            'khasra_code': self.khasra_code,
            'khasra_no': self.khasra_no,
            'nakal_villege': self.nakal_villege,
            'nakal_hadbast': self.nakal_hadbast,
            'nakal_tehsil': self.nakal_tehsil,
            'nakal_district': self.nakal_district,
            'nakal_year': self.nakal_year,
            'created_at': format_datetime(self.created_at),
            'updated_at': format_datetime(self.updated_at),
        }

# Creating sqlalchemy engine and binding it to a database
engine = create_engine('sqlite:///land_records.db')

# Create tables in the database
Base.metadata.create_all(engine)

# Create a session
Session = sessionmaker(bind=engine)
db_session = Session()

# Example of how to insert a record
# new_record = LandRecord(
#     district_name='अम्बाला',
#     district_code='01',
#     tehsil_name='अम्बाला',
#     tehsil_code='001',
#     villege_name='अम्बालाशहर',
#     villege_code='02848',
#     jamabandi_year='2022-2023',
#     khewat_no='3',
#     khatoni_no='9',
#     khasra_code='6',
#     khasra_no='6',
    
#     nakal_villege='अम्बालाशहर',
#     nakal_hadbast='50',
#     nakal_tehsil='अम्बाला',
#     nakal_district='अम्बाला',
#     nakal_year='2022-2023'
# )

# db_session.add(new_record)
# db_session.commit()
