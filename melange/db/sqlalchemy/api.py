# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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

import logging

import netaddr

import sqlalchemy.exc
from sqlalchemy import and_
from sqlalchemy import or_
from sqlalchemy.orm import aliased
from sqlalchemy.orm import clear_mappers

from melange import ipam
from melange.common import exception
from melange.common import utils
from melange.db.sqlalchemy import migration
from melange.db.sqlalchemy import mappers
from melange.db.sqlalchemy import session


LOG = logging.getLogger(__name__)


def list(query_func, *args, **kwargs):
    return query_func(*args, **kwargs).all()


def count(query, *args, **kwargs):
    return query(*args, **kwargs).count()


def find_all(model, **conditions):
    return _query_by(model, **conditions)


def find_all_by_limit(query_func, model, conditions, limit, marker=None,
                      marker_column=None):
    return _limits(query_func, model, conditions, limit, marker,
                   marker_column).all()


def find_by(model, **kwargs):
    return _query_by(model, **kwargs).first()


def save(model, db_session=None):
    try:
        if not db_session:
            db_session = session.get_session()
        model = db_session.merge(model)
        db_session.flush()
        return model
    except sqlalchemy.exc.IntegrityError as error:
        raise exception.DBConstraintError(model_name=model.__class__.__name__,
                                          error=str(error.orig))


def delete(model, db_session=None):
    db_session = db_session or session.get_session()
    model = db_session.merge(model)
    db_session.delete(model)
    db_session.flush()


def delete_all(query_func, model, **conditions):
    query_func(model, **conditions).delete()


def update(model, **values):
    for k, v in values.iteritems():
        model[k] = v


def update_all(query_func, model, conditions, values):
    query_func(model, **conditions).update(values)


def find_inside_globals(ip_model, local_address_id, **kwargs):
    ip_nat = mappers.IpNat
    return _base_query(ip_model).\
        join(ip_nat, ip_nat.inside_global_address_id == ip_model.id).\
        filter(ip_nat.inside_local_address_id == local_address_id)


def find_inside_locals(ip_model, global_address_id, **kwargs):
    ip_nat = mappers.IpNat
    return _base_query(ip_model).\
        join(ip_nat, ip_nat.inside_local_address_id == ip_model.id).\
        filter(ip_nat.inside_global_address_id == global_address_id)


def save_nat_relationships(nat_relationships):
    for relationship in nat_relationships:
        ip_nat = mappers.IpNat()
        relationship['id'] = utils.generate_uuid()
        update(ip_nat, **relationship)
        save(ip_nat)


def remove_inside_globals(local_address_id, inside_global_address=None):

    def _filter_inside_global_address(natted_ips, inside_global_address):
        return natted_ips.join(
            (ipam.models.IpAddress,
             mappers.IpNat.inside_global_address_id ==
             ipam.models.IpAddress.id)).filter(
                 ipam.models.IpAddress.address == inside_global_address)

    _remove_natted_ips(_filter_inside_global_address,
                       inside_global_address,
                       inside_local_address_id=local_address_id)


def remove_inside_locals(global_address_id, inside_local_address=None):

    def _filter_inside_local_address(natted_ips, inside_local_address):
        return natted_ips.join(
            (ipam.models.IpAddress,
             mappers.IpNat.inside_local_address_id ==
             ipam.models.IpAddress.id)).filter(ipam.models.IpAddress.address ==
                                               inside_local_address)

    _remove_natted_ips(_filter_inside_local_address,
                       inside_local_address,
                       inside_global_address_id=global_address_id)


def _remove_natted_ips(filter_by_natted_address_func,
                       natted_address, **kwargs):
    natted_ips = find_natted_ips(**kwargs)
    if natted_address is not None:
        natted_ips = filter_by_natted_address_func(natted_ips, natted_address)
    for ip in natted_ips:
        delete(ip)


def find_natted_ips(**kwargs):
    return _base_query(mappers.IpNat).filter_by(**kwargs)


def find_all_blocks_with_deallocated_ips():
    deallocate = True
    return _base_query(ipam.models.IpBlock).\
        join(ipam.models.IpAddress).\
        filter(ipam.models.IpAddress.marked_for_deallocation
               == deallocate)


def find_deallocated_ips(deallocated_by, **kwargs):
    return _query_by(ipam.models.IpAddress, **kwargs).\
        filter_by(marked_for_deallocation=True).\
        filter(ipam.models.IpAddress.deallocated_at <= deallocated_by).all()


def find_all_top_level_blocks_in_network(network_id):
    parent_block = aliased(ipam.models.IpBlock, name="parent_block")
    id = None

    return _base_query(ipam.models.IpBlock).\
        outerjoin((parent_block,
                   and_(ipam.models.IpBlock.parent_id == parent_block.id,
                        parent_block.network_id == network_id))).\
        filter(ipam.models.IpBlock.network_id == network_id).\
        filter(parent_block.id == id)


def find_all_ips_in_network(model, network_id=None, **conditions):
    return _query_by(ipam.models.IpAddress, **conditions).\
        join(ipam.models.IpBlock).\
        filter(ipam.models.IpBlock.network_id == network_id)


def find_all_addresses(ip_block_id):
    query = _query_by(ipam.models.IpAddress, ip_block_id=ip_block_id)
    query = query.filter(or_(ipam.models.IpAddress.allocated,
                             ipam.models.IpAddress.marked_for_deallocation))
    return query


def find_all_allocated_ips(_model, used_by_device=None,
                           used_by_tenant=None, address=None,
                           interface_id=None):
    deallocated_on = None
    query = _query_by(ipam.models.IpAddress)
    allocated = or_(ipam.models.IpAddress.marked_for_deallocation
                    == deallocated_on,
                    ipam.models.IpAddress.marked_for_deallocation is False)
    query = query.filter(allocated)

    if interface_id is not None:
        query = query.filter_by(interface_id=interface_id)

    if address is not None:
        query = query.filter_by(address=address)

    if used_by_device or used_by_tenant:
        query = query.join(ipam.models.Interface)
    if used_by_device:
        query = query.filter(ipam.models.Interface.device_id == used_by_device)
    if used_by_tenant:
        query = query.filter(ipam.models.Interface.tenant_id == used_by_tenant)

    return query


def delete_interface(interface):
    db_session = session.get_session()
    with db_session.begin():
        mac_qry = _query_by(ipam.models.MacAddress, db_session=db_session,
                            interface_id=interface.id)

        mac = mac_qry.with_lockmode('update').first()

        if mac:
            db_session.delete(mac)

        ips_qry = _query_by(ipam.models.IpAddress, db_session=db_session,
                            interface_id=interface.id)
        ips = ips_qry.with_lockmode('update').all()

        for ip in ips:
            LOG.debug("Marking IP address for deallocation: %r" % ip)
            ip.allocated = False
            ip.marked_for_deallocation = True
            ip.deallocated_at = utils.utcnow()
            ip.interface_id = None
            db_session.merge(ip)

        db_session.delete(interface)

        return mac, ips

    # NOTE(jkoelker) Failsafe return:
    return None, []


def allocate_ipv4_address(ip_block, interface, requested_address=None):
    model = ipam.models.IpAddress

    db_session = session.get_session()
    with db_session.begin():
        address_qry = _query_by(model, db_session=db_session,
                                allocated=False, ip_block_id=ip_block.id)

        if requested_address is not None:
            address_qry = address_qry.filter(address=requested_address)

        address = address_qry.with_lockmode('update').first()

        if address:
            address.allocated = True
            address.interface_id = interface.id
            address.used_by_tenant_id = interface.tenant_id
            address.updated_at = utils.utcnow()
            db_session.merge(address)
            return address

        # NOTE(jkoelker) This is here so we can slowly move off the table
        allocatable_qry = _query_by(ipam.models.AllocatableIp,
                                    db_session=db_session,
                                    ip_block_id=ip_block.id)
        if requested_address is not None:
            filter_kwargs = {'address': requested_address}
            allocatable_qry = allocatable_qry.filter(**filter_kwargs)

        address = allocatable_qry.first()
        if address:
            ip = address.address
            db_session.delete(address)

        else:
            ips = netaddr.IPNetwork(ip_block.cidr)
            counter = (ip_block.allocatable_ip_counter or ips[0].value)

            if counter > ips[-1].value:
                ip_block.is_full = True
                # NOTE(jkoelker) explicit save() to flush the session prior
                #                to raising
                save(ip_block, db_session=db_session)
                raise exception.NoMoreAddressesError(_("IpBlock is full"))

            ip = netaddr.IPAddress(counter)

            # NOTE(jkoelker) HRM, this may need to be rethought order wise
            counter = counter + 1
            if counter > ips[-1].value:
                ip_block.is_full = True

            ip_block.allocatable_ip_counter = counter
            db_session.merge(ip_block)

        # NOTE(jkoelker) SQLAlchemy models, how do you work? ;)
        address = model(id=utils.generate_uuid(),
                        created_at=utils.utcnow(),
                        updated_at=utils.utcnow(),
                        address=str(ip),
                        ip_block_id=ip_block.id,
                        interface_id=interface.id,
                        used_by_tenant_id=interface.tenant_id,
                        allocated=True)
        db_session.merge(address)

        return address


def pop_allocatable_address(address_model, **conditions):
    db_session = session.get_session()
    with db_session.begin():
        address_rec = _query_by(
            address_model,
            db_session=db_session,
            **conditions).with_lockmode('update').first()
        if not address_rec:
            return None

        delete(address_rec, db_session=db_session)
        return address_rec.address


def save_allowed_ip(interface_id, ip_address_id):
    allowed_ip = mappers.AllowedIp()
    update(allowed_ip,
           id=utils.generate_uuid(),
           interface_id=interface_id,
           ip_address_id=ip_address_id)
    save(allowed_ip)


def find_allowed_ips(ip_address_model,
                     allowed_on_interface_id=None,
                     **conditions):
    query = _query_by(ip_address_model).\
        join(mappers.AllowedIp).filter_by(**conditions)

    if allowed_on_interface_id:
        query = query.filter(
            mappers.AllowedIp.interface_id == allowed_on_interface_id)

    return query


def remove_allowed_ip(**conditions):
    _query_by(mappers.AllowedIp).\
        filter_by(**conditions).\
        delete()


def configure_db(options, *plugins):
    session.configure_db(options)
    configure_db_for_plugins(options, *plugins)


def configure_db_for_plugins(options, *plugins):
    for plugin in plugins:
        session.configure_db(options, models_mapper=plugin.mapper)


def drop_db(options):
    session.drop_db(options)


def clean_db():
    session.clean_db()


def db_sync(options, version=None, repo_path=None):
    migration.db_sync(options, version, repo_path)


def db_upgrade(options, version=None, repo_path=None):
    migration.upgrade(options, version, repo_path)


def db_downgrade(options, version, repo_path=None):
    migration.downgrade(options, version, repo_path)


def db_reset(options, *plugins):
    drop_db(options)
    db_sync(options)
    # NOTE(jkoelker) This is bad, but the only way for the models to pick
    #                up columns added in the migrations for unittests
    clear_mappers()
    db_reset_for_plugins(options, *plugins)
    configure_db(options)


def db_reset_for_plugins(options, *plugins):
    for plugin in plugins:
        repo_path = plugin.migrate_repo_path()
        if repo_path:
            db_sync(options, repo_path=repo_path)
    configure_db(options, *plugins)


def _base_query(cls):
    return session.get_session().query(cls)


def _query_by(cls, db_session=None, **conditions):
    if db_session:
        query = db_session.query(cls)
    else:
        query = _base_query(cls)
    if conditions:
        query = query.filter_by(**conditions)
    return query


def _limits(query_func, model, conditions, limit, marker, marker_column=None):
    query = query_func(model, **conditions)
    marker_column = marker_column or model.id
    if marker:
        query = query.filter(marker_column > marker)
    return query.order_by(marker_column).limit(limit)
