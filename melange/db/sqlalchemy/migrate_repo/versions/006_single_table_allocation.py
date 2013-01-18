#!/usr/bin/env python

# Copyright 2012 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from sqlalchemy.schema import Column
from sqlalchemy.schema import MetaData
from sqlalchemy.schema import Table

from melange.db.sqlalchemy.migrate_repo.schema import Boolean


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    ip_addresses = Table('ip_addresses', meta, autoload=True)
    allocated = Column('allocated', Boolean(), default=False)
    ip_addresses.create_column(allocated)
    migrate_engine.execute(ip_addresses.update().values(allocated=True))


def downgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    ip_addresses = Table('ip_addresses', meta, autoload=True)
    ip_addresses.drop_column('allocated')
