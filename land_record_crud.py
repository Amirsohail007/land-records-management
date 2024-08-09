from models import LandRecord


class LandRecordCRUD:
    def __init__(self, session):
        self.session = session

    def create_record(self, **kwargs):
        """
        Create a new LandRecord record.
        """
        record = LandRecord(**kwargs)
        self.session.add(record)
        self.session.commit()
        return record.to_dict()
    
    def create_record_by_checking_record(
        self, district_name: str, tehsil_name: str, villege_name: str, 
        khasra_no: str, data: dict, force_refresh: bool=False) -> dict:
        """
        Create a new LandRecord record if the query for district_name, tehsil_name, villege_name, khasra_no will return empty or None.
        """
        nakal_data = self.search_records_by_input_data(
            district_name=district_name, tehsil_name=tehsil_name,
            villege_name=villege_name, khasra_no=khasra_no
            )
        if nakal_data:
            nakal_data = nakal_data[0]
        if nakal_data and not force_refresh:
            return nakal_data
        elif nakal_data and force_refresh:
            return self.update_record(record_id=nakal_data['id'], data=data)
        record = LandRecord(**data)
        self.session.add(record)
        self.session.commit()
        return record.to_dict()

    def read_record(self, record_id: int) -> dict:
        """
        Read a LandRecord record by its ID.
        """
        data = self.session.query(LandRecord).filter_by(id=record_id).first()
        return data.to_dict() if data else {}

    def update_record(self, record_id: int, data: dict) -> dict|None:
        """
        Update a LandRecord record by its ID.
        """
        record = self.session.query(LandRecord).filter_by(id=record_id).first()
        if record:
            for key, value in data.items():
                setattr(record, key, value)
            self.session.commit()
            return record.to_dict()
        return None

    def delete_record(self, record_id: id) -> bool:
        """
        Delete a LandRecord record by its ID.
        """
        record = self.session.query(LandRecord).filter_by(id=record_id).first()
        if record:
            self.session.delete(record)
            self.session.commit()
            return True
        return False

    def search_records(self, district_name: str=None, 
                       tehsil_name: str=None, villege_name: str=None) -> list:
        """
        Search LandRecord records based on provided criteria.
        """
        query = self.session.query(LandRecord)
        if district_name:
            query = query.filter_by(district_name=district_name)
        if tehsil_name:
            query = query.filter_by(tehsil_name=tehsil_name)
        if villege_name:
            query = query.filter_by(villege_name=villege_name)
        data = query.all()
        return [item.to_dict() for item in data] if data else []
    
    def search_records_by_input_data(self, district_name: str, tehsil_name: str, 
                                    villege_name: str, khasra_no: str) -> list:
        """
        Read all LandRecord record by district_name, tehsil_name, villege_name and khasra_no.
        """
        data = self.session.query(LandRecord).filter_by(
            district_name=district_name, tehsil_name=tehsil_name, 
            villege_name=villege_name, khasra_no=khasra_no).all()
        return [item.to_dict() for item in data] if data else []
