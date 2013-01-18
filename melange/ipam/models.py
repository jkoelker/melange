# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http: //www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Model classes that form the core of ipam functionality."""

import datetime
import logging
import netaddr
import operator

from melange import db
from melange import ipv6
from melange import mac
from melange.common import config
from melange.common import exception
from melange.common import notifier
from melange.common import utils


LOG = logging.getLogger('melange.ipam.models')


# Hours spent emulating sqlalchemy: 5


class ModelBase(object):

    _fields_for_type_conversion = {}
    _auto_generated_attrs = ["id", "created_at", "updated_at"]
    _data_fields = []
    on_create_notification_fields = []
    on_update_notification_fields = []
    on_delete_notification_fields = []

    @classmethod
    def create(cls, **values):
        values['id'] = utils.generate_uuid()
        values['created_at'] = utils.utcnow()
        instance = cls(**values).save()
        instance._notify_fields("create")
        return instance

    def _notify_fields(self, event):
        fields = getattr(self, "on_%s_notification_fields" % event)
        if not fields:
            return
        payload = self._notification_payload(fields)
        event_with_model_name = event + " " + self.__class__.__name__
        notifier.notifier().info(event_with_model_name, payload)

    def _notification_payload(self, fields):
        return dict((attr, getattr(self, attr)) for attr in fields)

    def update(self, **values):
        attrs = utils.exclude(values, *self._auto_generated_attrs)
        self.merge_attributes(attrs)
        result = self.save()
        self._notify_fields("update")
        return result

    def save(self):
        if not self.is_valid():
            raise InvalidModelError(self.errors)
        self._convert_columns_to_proper_type()
        self._before_save()
        self['updated_at'] = utils.utcnow()
        LOG.debug("Saving %s: %s" % (self.__class__.__name__, self.__dict__))
        return db.db_api.save(self)

    def delete(self):
        db.db_api.delete(self)
        self._notify_fields("delete")

    def __init__(self, **kwargs):
        self.merge_attributes(kwargs)

    def _validate_columns_type(self):
        fields = self._fields_for_type_conversion
        for field_name, data_type in fields.iteritems():
            try:
                Converter(data_type).convert(self[field_name])
            except (TypeError, ValueError):
                self._add_error(
                    field_name,
                    _("%(field_name)s should be of type %(data_type)s")
                    % locals())

    def _validate(self):
        pass

    def _before_validate(self):
        pass

    def _before_save(self):
        pass

    def _convert_columns_to_proper_type(self):
        fields = self._fields_for_type_conversion
        for field_name, data_type in fields.iteritems():
            self[field_name] = Converter(data_type).convert(self[field_name])

    def is_valid(self):
        self.errors = {}
        self._validate_columns_type()
        self._before_validate()
        self._validate()
        return self.errors == {}

    def _validate_presence_of(self, *attribute_names):
        for attribute_name in attribute_names:
            if self[attribute_name] in [None, ""]:
                self._add_error(attribute_name,
                                _("%(attribute_name)s should be present")
                                % locals())

    def _validate_existence_of(self, attribute, model_class, **conditions):
        model_id = self[attribute]
        conditions['id'] = model_id
        if model_id and model_class.get_by(**conditions) is None:
            args = {}
            args["conditions_str"] = ", ".join(
                ["{0} = {1}".format(key, repr(value))
                 for key, value in conditions.iteritems()])
            args["model_class_name"] = model_class.__name__
            msg = _("%(model_class_name)s with %(conditions_str)s"
                    " doesn't exist") % args
            self._add_error(attribute, msg)

    @classmethod
    def find(cls, id):
        return cls.find_by(id=id)

    @classmethod
    def get(cls, id):
        return cls.get_by(id=id)

    @classmethod
    def find_by(cls, **conditions):
        model = cls.get_by(**conditions)
        if model is None:
            raise ModelNotFoundError(_("%s Not Found") % cls.__name__)
        return model

    @classmethod
    def get_by(cls, **kwargs):
        return db.db_api.find_by(cls, **cls._process_conditions(kwargs))

    @classmethod
    def _process_conditions(cls, raw_conditions):
        """Override in inheritors to format/modify any conditions."""
        return raw_conditions

    @classmethod
    def find_all(cls, **kwargs):
        return db.db_query.find_all(cls, **cls._process_conditions(kwargs))

    @classmethod
    def count(cls, **conditions):
        return cls.find_all(**conditions).count()

    def merge_attributes(self, values):
        """dict.update() behaviour."""
        for k, v in values.iteritems():
            self[k] = v

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def __getitem__(self, key):
        return getattr(self, key)

    def __eq__(self, other):
        if not hasattr(other, 'id'):
            return False
        return type(other) == type(self) and other.id == self.id

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return self.id.__hash__()

    def data(self, **options):
        data_fields = self._data_fields + self._auto_generated_attrs
        return dict([(field, self[field]) for field in data_fields])

    def _validate_positive_integer(self, attribute_name):
        if utils.parse_int(self[attribute_name]) < 0:
            self._add_error(attribute_name,
                            _("%s should be a positive integer")
                            % attribute_name)

    def _add_error(self, attribute_name, error_message):
        self.errors[attribute_name] = self.errors.get(attribute_name, [])
        self.errors[attribute_name].append(error_message)


class Converter(object):

    data_type_converters = {
        'integer': lambda value: int(value),
        'boolean': lambda value: utils.bool_from_string(value),
    }

    def __init__(self, data_type):
        self.data_type = data_type

    def convert(self, value):
        return self.data_type_converters[self.data_type](value)


class IpAddressIterator(object):

    def __init__(self, generator):
        self.generator = generator

    def __iter__(self):
        return self

    def next(self):
        try:
            return self.generator.next_ip()
        except exception.NoMoreAddressesError:
            raise StopIteration


def deallocated_by_date():
    days = config.Config.get('keep_deallocated_ips_for_days')
    if days is None:
        seconds = config.Config.get('keep_deallocated_ips_for_seconds', 172800)
    else:
        seconds = int(days) * 86400
    LOG.debug("Delete delay = ", seconds)
    return utils.utcnow() - datetime.timedelta(seconds=int(seconds))


class IpBlock(ModelBase):

    PUBLIC_TYPE = "public"
    PRIVATE_TYPE = "private"
    _allowed_block_types = [PUBLIC_TYPE, PRIVATE_TYPE]
    _data_fields = ['cidr', 'network_id', 'policy_id', 'tenant_id', 'gateway',
                    'parent_id', 'type', 'dns1', 'dns2', 'broadcast',
                    'netmask', 'percent_used', 'ips_used', 'network_name',
                    'max_allocation']
    on_create_notification_fields = ['tenant_id', 'id', 'type', 'created_at']
    on_delete_notification_fields = ['tenant_id', 'id', 'type', 'created_at']

    @classmethod
    def find_allocated_ip(cls, ip_block_id, tenant_id, **conditions):
        block = IpBlock.find_by(id=ip_block_id, tenant_id=tenant_id)
        allocated_ip = block.find_ip(**conditions)
        if allocated_ip.locked():
            raise AddressLockedError()
        return allocated_ip

    @classmethod
    def delete_all_deallocated_ips(
            cls,
            deallocated_by_func=deallocated_by_date):
        LOG.info("Deleting all deallocated IPs")
        for block in db.db_api.find_all_blocks_with_deallocated_ips():
            block.delete_deallocated_ips(deallocated_by_func)

    @property
    def broadcast(self):
        return str(netaddr.IPNetwork(self.cidr).broadcast)

    @property
    def netmask(self):
        if self.is_ipv6():
            return str(netaddr.IPNetwork(self.cidr).prefixlen)
        else:
            return str(netaddr.IPNetwork(self.cidr).netmask)

    @property
    def ips_used(self):
        allocated_count = IpAddress.find_all(ip_block_id=self.id,
                                             allocated=True).count()
        if self.policy_id:
            reserved = self.policy().size(self.cidr)
        else:
            reserved = 0
        return allocated_count + reserved

    @property
    def percent_used(self):
        return (float(self.ips_used) / self.size()) * 100.0

    def is_ipv6(self):
        return netaddr.IPNetwork(self.cidr).version == 6

    def subnets(self):
        return IpBlock.find_all(parent_id=self.id).all()

    def size(self):
        return netaddr.IPNetwork(self.cidr).size

    def siblings(self):
        if not self.parent:
            return []
        return filter(lambda block: block != self, self.parent.subnets())

    def delete(self):
        for block in self.subnets():
            block.delete()
        IpAddress.find_all(ip_block_id=self.id).delete()
        super(IpBlock, self).delete()

    def policy(self):
        return Policy.get(self.policy_id)

    def ip_routes(self):
        return IpRoute.find_all(source_block_id=self.id)

    def does_address_exists(self, address):
        return (address in [self.broadcast, self.gateway]
                or IpAddress.get_by(ip_block_id=self.id,
                                    address=address,
                                    allocated=True) is not None)

    def addresses(self):
        # NOTE(jkoelker) needless abstraction is needless
        return db.db_api.find_all_addresses(self.id).all()

    @utils.cached_property
    def parent(self):
        return IpBlock.get(self.parent_id)

    def no_ips_allocated(self):
        return IpAddress.find_all(ip_block_id=self.id).count() == 0

    def allocate_ip(self, interface, address=None, **kwargs):

        if self.subnets():
            raise IpAllocationNotAllowedError(
                _("Subnetted block cannot allocate IPAddress"))
        if self.is_full:
            raise exception.NoMoreAddressesError(_("IpBlock is full"))

        interface_network = interface.plugged_in_network_id()
        if (interface_network is not None
                and interface_network != self.network_id):
            raise IpAllocationNotAllowedError(
                _("Interface %s is configured on another network")
                % interface.virtual_interface_id)

        if address:
            return self._allocate_specific_ip(interface, address)
        return self._allocate_available_ip(interface, **kwargs)

    def _allocate_available_ip(self, interface, **kwargs):

        def clear_addresses(addresses):
            for address in addresses:
                address.update(allocated=False, interface_id=None,
                               used_by_tenant_id=None)
                address.save()

        max_allowed_retry = int(config.Config.get("ip_allocation_retries",
                                                  10))

        tenant_id = interface.tenant_id
        policy_excluded_addresses = []

        for retries in xrange(max_allowed_retry):
            try:
                if self.is_ipv6():
                    mac_address = interface.mac_address_eui_format
                    return self._allocate_ipv6(tenant_id,
                                               interface.id,
                                               used_by_tenant=tenant_id,
                                               mac_address=mac_address,
                                               **kwargs)

                address = IpAddress.allocate(ip_block=self,
                                             interface=interface)
                if not address:
                    self.update(is_full=True)
                    msg = _("IpBlock is full")
                    raise exception.NoMoreAddressesError(msg)

                # NOTE(jkoelker) policy enforcement is no-bueno ;(
                if not self._address_is_allocatable(self.policy(),
                                                    address.address):
                    policy_excluded_addresses.append(address)
                    continue

                clear_addresses(policy_excluded_addresses)
                return address

            except exception.DBConstraintError:
                count = retries + 1
                msg = "IP allocation retry count :{0}".format(count)
                LOG.exception(msg)

        clear_addresses(policy_excluded_addresses)
        msg = _("Cannot allocate address for block %s at this time")
        raise ConcurrentAllocationError(msg % self.id)

    def _allocate_ipv6(self, tenant_id, interface_id, **kwargs):
        factory = ipv6.address_generator_factory

        generator = factory(self.cidr, **kwargs)

        address_iter = (addr for addr in IpAddressIterator(generator)
                        if self.does_address_exists(addr) is False)

        address = next(address_iter, None)

        if not address:
            self.update(is_full=True)
            msg = _("IpBlock is full")
            raise exception.NoMoreAddressesError(msg)

        return IpAddress.create(address=address,
                                ip_block_id=self.id,
                                used_by_tenant_id=tenant_id,
                                interface_id=interface_id,
                                allocated=True)

    def _allocate_specific_ip(self, interface, address):

        if not self.contains(address):
            raise AddressDoesNotBelongError(
                _("Address does not belong to IpBlock"))

        if self.does_address_exists(address):
            raise DuplicateAddressError()

        if not self._allowed_by_policy(self.policy(), address):
            raise AddressDisallowedByPolicyError(
                _("Block policy does not allow this address"))

        ip = IpAddress.get_by(ip_block_id=self.id, address=address)

        if ip and (ip.allocated or ip.marked_for_deallocation):
            raise DuplicateAddressError()

        if self.is_ipv6() or not ip:
            return IpAddress.create(address=address,
                                    ip_block_id=self.id,
                                    used_by_tenant_id=interface.tenant_id,
                                    interface_id=interface.id,
                                    allocated=True)
        return IpAddress.allocate(self, interface, address=address)

    def _address_is_allocatable(self, policy, address):
        unavailable_addresses = [self.gateway, self.broadcast]
        return (address not in unavailable_addresses
                and self._allowed_by_policy(policy, address))

    def _allowed_by_policy(self, policy, address):
        return policy is None or policy.allows(self.cidr, address)

    def contains(self, address):
        return netaddr.IPAddress(address) in netaddr.IPNetwork(self.cidr)

    def _overlaps(self, other_block):
        network = netaddr.IPNetwork(self.cidr)
        other_network = netaddr.IPNetwork(other_block.cidr)
        return network in other_network or other_network in network

    def find_ip(self, **kwargs):
        LOG.debug("Searching for IP block %r for IP matching "
                  "%s" % (self.id, kwargs))
        return IpAddress.find_by(ip_block_id=self.id, **kwargs)

    def deallocate_ip(self, address):
        ip_address = IpAddress.find_by(ip_block_id=self.id, address=address)
        if isinstance(ip_address, IpAddress):
            LOG.debug("Deallocating IP: %s" % ip_address)
            ip_address.deallocate()

    # TODO(jkoelker) This should probably move into the dbapi so it can
    #                bulk deallocate
    def delete_deallocated_ips(self, deallocated_by_func):
        for ip in db.db_api.find_deallocated_ips(
                deallocated_by=deallocated_by_func(), ip_block_id=self.id):
            LOG.debug("Deleting deallocated IP: %s" % ip)

            if self.is_ipv6():
                ip.delete()
                continue

            # NOTE(jkoelker) Single table ipv4 deallocation
            ip.used_by_tenant_id = None
            ip.allocated = False
            ip.marked_for_deallocation = False
            ip.save()

            # NOTE(jkoelker) continue to notify on delete since that
            #                means deallocated.
            ip._notify_fields("delete")

        self.update(is_full=False)

    def subnet(self, cidr, network_id=None, tenant_id=None,
               network_name=None):
        network_id = network_id or self.network_id
        network_name = network_name or self.network_name
        tenant_id = tenant_id or self.tenant_id
        return IpBlock.create(cidr=cidr,
                              network_id=network_id,
                              network_name=network_name,
                              parent_id=self.id,
                              type=self.type,
                              tenant_id=tenant_id)

    def _validate_cidr_format(self):
        if not self._has_valid_cidr():
            self._add_error('cidr', _("cidr is invalid"))

    def _has_valid_cidr(self):
        try:
            netaddr.IPNetwork(self.cidr)
            return True
        except Exception:
            return False

    def _validate_cidr_is_within_parent_block_cidr(self):
        parent = self.parent
        if (parent and netaddr.IPNetwork(self.cidr) not in
                netaddr.IPNetwork(parent.cidr)):
            self._add_error('cidr',
                            _("cidr should be within parent block's cidr"))

    def _validate_type(self):
        if self.type not in self._allowed_block_types:
            self._add_error('type', _("type should be one among %s") %
                            ", ".join(self._allowed_block_types))

    def _validate_cidr(self):
        self._validate_cidr_format()
        if not self._has_valid_cidr():
            return
        self._validate_cidr_doesnt_overlap_for_root_public_ip_blocks()
        self._validate_cidr_is_within_parent_block_cidr()
        self._validate_cidr_does_not_overlap_with_siblings()
        if self._is_top_level_block_in_network():
            self._validate_cidr_doesnt_overlap_with_networked_toplevel_blocks()

    def _validate_cidr_doesnt_overlap_for_root_public_ip_blocks(self):
        if self.type != self.PUBLIC_TYPE:
            return
        for block in IpBlock.find_all(type=self.PUBLIC_TYPE, parent_id=None):
            if self != block and self._overlaps(block):
                msg = _("cidr overlaps with public block %s") % block.cidr
                self._add_error('cidr', msg)
                break

    def _validate_cidr_does_not_overlap_with_siblings(self):
        for sibling in self.siblings():
            if self._overlaps(sibling):
                msg = _("cidr overlaps with sibling %s") % sibling.cidr
                self._add_error('cidr', msg)
                break

    def networked_top_level_blocks(self):
        if not self.network_id:
            return []
        blocks = db.db_api.find_all_top_level_blocks_in_network(
            self.network_id)
        return filter(lambda block: block != self and block != self.parent,
                      blocks)

    def _is_top_level_block_in_network(self):
        return not self.parent or self.network_id != self.parent.network_id

    def _validate_cidr_doesnt_overlap_with_networked_toplevel_blocks(self):
        for block in self.networked_top_level_blocks():
            if self._overlaps(block):
                self._add_error('cidr', _("cidr overlaps with block %s"
                                          " in same network") % block.cidr)
                break

    def _validate_belongs_to_supernet_network(self):
        if (self.parent and self.parent.network_id and
                self.parent.network_id != self.network_id):
            self._add_error('network_id',
                            _("network_id should be same as that of parent"))

    def _validate_parent_is_subnettable(self):
        if self.parent and self.parent.addresses():
            msg = _("parent is not subnettable since it has allocated ips")
            self._add_error('parent_id', msg)

    def _validate_type_is_same_within_network(self):
        if not self.network_id:
            return
        block = IpBlock.get_by(network_id=self.network_id)
        if block and block.type != self.type:
            self._add_error('type', _("type should be same within a network"))

    def _validate_gateway_is_valid(self):
        if self.gateway:
            try:
                netaddr.IPAddress(self.gateway)
            except netaddr.core.AddrFormatError:
                self._add_error('gateway', _("Gateway is not a valid address"))

    def _validate(self):
        self._validate_type()
        self._validate_cidr()
        self._validate_presence_of('tenant_id')
        self._validate_existence_of('parent_id', IpBlock, type=self.type)
        self._validate_belongs_to_supernet_network()
        self._validate_parent_is_subnettable()
        self._validate_existence_of('policy_id', Policy)
        self._validate_type_is_same_within_network()
        self._validate_gateway_is_valid()

    def _convert_cidr_to_lowest_address(self):
        if self._has_valid_cidr():
            self.cidr = str(netaddr.IPNetwork(self.cidr).cidr)

    def _before_validate(self):
        self._convert_cidr_to_lowest_address()

    def _before_save(self):
        self.dns1 = self.dns1 or config.Config.get("dns1")
        self.dns2 = self.dns2 or config.Config.get("dns2")


# NOTE(jkoelker) This is here so we can slowly move off the table
class AllocatableIp(ModelBase):
    pass


class IpAddress(ModelBase):

    _data_fields = ['ip_block_id', 'address', 'version']
    on_create_notification_fields = ['used_by_tenant_id', 'id', 'ip_block_id',
                                     'used_by_device_id', 'created_at',
                                     'address']
    on_delete_notification_fields = ['used_by_tenant_id', 'id', 'ip_block_id',
                                     'used_by_device_id', 'created_at',
                                     'address']

    def _validate(self):
        if self.allocated:
            self._validate_presence_of("used_by_tenant_id")
        if self.interface_id:
            self._validate_existence_of("interface_id", Interface)

    @classmethod
    def _process_conditions(cls, raw_conditions):
        conditions = raw_conditions.copy()
        if 'address' in conditions:
            conditions['address'] = cls._formatted(conditions['address'])
        return conditions

    @classmethod
    def _formatted(cls, address):
        ipv6_format_dialect = netaddr.strategy.ipv6.ipv6_verbose
        return netaddr.IPAddress(address).format(dialect=ipv6_format_dialect)

    @classmethod
    def find_all_by_network(cls, network_id, **conditions):
        LOG.debug("Retrieving all IPs for network %s" % network_id)
        return db.db_query.find_all_ips_in_network(
            cls,
            network_id=network_id,
            **conditions)

    @classmethod
    def find_all_allocated_ips(cls, **conditions):
        LOG.debug("Retrieving all allocated IPs.")
        return db.db_query.find_all_allocated_ips(cls, **conditions)

    @classmethod
    def allocate(cls, ip_block, interface, address=None):
        address = db.db_api.allocate_ipv4_address(ip_block,
                                                  interface,
                                                  address)
        # NOTE(jkoelker) Continue to notify on create since that
        #                means allocation.
        address._notify_fields('create')
        return address

    def delete(self):
        LOG.debug("Deleting IP address: %r" % self)
        if self._explicitly_allowed_on_interfaces():
            return self.update(marked_for_deallocation=False,
                               allocated=False,
                               deallocated_at=None,
                               interface_id=None)

        super(IpAddress, self).delete()

    def _explicitly_allowed_on_interfaces(self):
        return db.db_query.find_allowed_ips(IpAddress,
                                            ip_address_id=self.id).count() > 0

    def _before_save(self):
        self.address = self._formatted(self.address)

    @utils.cached_property
    def ip_block(self):
        return IpBlock.get(self.ip_block_id)

    def add_inside_locals(self, ip_addresses):
        db.db_api.save_nat_relationships([
            {'inside_global_address_id': self.id,
             'inside_local_address_id': local_address.id,
             }
            for local_address in ip_addresses])

    def deallocate(self):
        LOG.debug("Marking IP address for deallocation: %r" % self)
        self.update(marked_for_deallocation=True,
                    allocated=False,
                    deallocated_at=utils.utcnow(),
                    interface=None)

    def restore(self):
        LOG.debug("Restored IP address: %r" % self)
        self.update(marked_for_deallocation=False, deallocated_at=None,
                    allocated=True)

    def inside_globals(self, **kwargs):
        return db.db_query.find_inside_globals(
            IpAddress,
            local_address_id=self.id,
            **kwargs)

    def add_inside_globals(self, ip_addresses):
        db.db_api.save_nat_relationships([
            {'inside_global_address_id': global_address.id,
             'inside_local_address_id': self.id,
             }
            for global_address in ip_addresses])

    def inside_locals(self, **kwargs):
        return db.db_query.find_inside_locals(IpAddress,
                                              global_address_id=self.id,
                                              **kwargs)

    def remove_inside_globals(self, inside_global_address=None):
        return db.db_api.remove_inside_globals(self.id, inside_global_address)

    def remove_inside_locals(self, inside_local_address=None):
        return db.db_api.remove_inside_locals(self.id, inside_local_address)

    def locked(self):
        return self.marked_for_deallocation

    @property
    def version(self):
        return netaddr.IPAddress(self.address).version

    @utils.cached_property
    def interface(self):
        return Interface.get(self.interface_id)

    @property
    def virtual_interface_id(self):
        return self.interface.virtual_interface_id if self.interface else None

    @utils.cached_property
    def mac_address(self):
        return MacAddress.get_by(interface_id=self.interface_id)

    @property
    def used_by_device_id(self):
        if self.interface:
            return self.interface.device_id

    def data(self, **options):
        data = super(IpAddress, self).data(**options)
        iface = self.interface
        data['used_by_tenant'] = iface.tenant_id
        data['used_by_device'] = iface.device_id
        data['interface_id'] = iface.virtual_interface_id
        return data

    def __str__(self):
        return self.address


class IpRoute(ModelBase):

    _data_fields = ['destination', 'netmask', 'gateway']

    def _validate(self):
        self._validate_presence_of("destination", "gateway")
        self._validate_existence_of("source_block_id", IpBlock)


class MacAddressRange(ModelBase):

    _data_fields = ['cidr']

    @classmethod
    def allocate_next_free_mac(cls, **kwargs):
        ranges = sorted(cls.find_all(),
                        key=operator.attrgetter('created_at', 'id'))
        for range in ranges:
            try:
                return range.allocate_mac(**kwargs)
            except NoMoreMacAddressesError:
                LOG.debug("no more addresses in range %s" % range.id)
        raise NoMoreMacAddressesError()

    @classmethod
    def mac_allocation_enabled(cls):
        return cls.count() > 0

    def allocate_mac(self, **kwargs):
        generator = mac.plugin().get_generator(self)
        if generator.is_full():
            raise NoMoreMacAddressesError()

        max_retry_count = int(config.Config.get("mac_allocation_retries", 10))
        for retries in range(max_retry_count):
            next_address = generator.next_mac()
            try:
                return MacAddress.create(address=next_address,
                                         mac_address_range_id=self.id,
                                         **kwargs)
            except exception.DBConstraintError as error:
                LOG.debug("MAC allocation retry count:{0}".format(retries + 1))
                LOG.exception(error)
                if generator.is_full():
                    raise NoMoreMacAddressesError()

        raise ConcurrentAllocationError(
            _("Cannot allocate mac address at this time"))

    def contains(self, address):
        address = int(netaddr.EUI(address))
        return (address >= self.first_address() and
                address <= self.last_address())

    def length(self):
        base_address, slash, prefix_length = self.cidr.partition("/")
        prefix_length = int(prefix_length)
        return 2 ** (48 - prefix_length)

    def first_address(self):
        base_address, slash, prefix_length = self.cidr.partition("/")
        prefix_length = int(prefix_length)
        netmask = (2 ** prefix_length - 1) << (48 - prefix_length)
        base_address = netaddr.EUI(base_address)
        return int(netaddr.EUI(int(base_address) & netmask))

    def last_address(self):
        return self.first_address() + self.length() - 1

    def no_macs_allocated(self):
        return MacAddress.find_all(mac_address_range_id=self.id).count() == 0


class MacAddress(ModelBase):

    @property
    def eui_format(self):
        return str(netaddr.EUI(self.address))

    @property
    def unix_format(self):
        return self.eui_format.replace('-', ':')

    def _before_save(self):
        self.address = int(netaddr.EUI(self.address))

    def _validate_belongs_to_mac_address_range(self):
        if self.mac_range:
            if not self.mac_range.contains(self.address):
                self._add_error('address', "address does not belong to range")

    def _validate(self):
        self._validate_belongs_to_mac_address_range()

    def delete(self):
        if self.mac_range:
            generator = mac.plugin().get_generator(self.mac_range)
            generator.mac_removed(self.address)
        super(MacAddress, self).delete()

    @utils.cached_property
    def mac_range(self):
        if self.mac_address_range_id:
            return MacAddressRange.find(self.mac_address_range_id)


class Interface(ModelBase):

    _data_fields = ["device_id", "tenant_id"]

    @classmethod
    def find_or_configure(cls, virtual_interface_id=None, device_id=None,
                          tenant_id=None, mac_address=None):
        interface = Interface.get_by(vif_id_on_device=virtual_interface_id,
                                     tenant_id=tenant_id)
        if interface:
            return interface

        return cls.create_and_configure(virtual_interface_id,
                                        device_id,
                                        tenant_id,
                                        mac_address)

    @classmethod
    def create_and_allocate_ips(cls,
                                device_id=None,
                                network_params=None,
                                **kwargs):
        interface = Interface.create_and_configure(device_id=device_id,
                                                   **kwargs)

        try:
            if network_params:
                network = Network.find_or_create_by(
                    network_params.pop('id'),
                    network_params.pop('tenant_id'))
                network.allocate_ips(interface=interface, **network_params)
        except NetworkOverQuotaError:
            interface.delete()
            raise
        return interface

    @classmethod
    def create_and_configure(cls, virtual_interface_id=None, device_id=None,
                             tenant_id=None, mac_address=None):
        interface = Interface.create(vif_id_on_device=virtual_interface_id,
                                     device_id=device_id,
                                     tenant_id=tenant_id)
        if mac_address:
            MacAddress.create(address=mac_address, interface_id=interface.id)
        elif MacAddressRange.mac_allocation_enabled():
            MacAddressRange.allocate_next_free_mac(interface_id=interface.id)
        return interface

    @classmethod
    def none_object(cls):
        return Interface(id=None, virtual_interface_id=None, device_id=None)

    def delete(self):
        mac_address, ips = db.db_api.delete_interface(self)

        if mac_address:
            if mac_address.mac_range:
                plugin = mac.plugin()
                generator = plugin.get_generator(mac_address.mac_range)
                generator.mac_removed(mac_address.address)
            # NOTE(jkoelker) notify that the mac was deleted
            mac_address._notify_fields("delete")

        for ip in ips:
            # NOTE(jkoelker) notify that the ips were deallocated
            ip._notify_fields("update")

    def data(self, **options):
        data = super(Interface, self).data()
        data['id'] = self.virtual_interface_id
        return data

    def allow_ip(self, ip):
        if self._ip_cannot_be_allowed(ip):
            err_msg = _("Ip %s cannot be allowed on interface %s as "
                        "interface is not configured "
                        "for ip's network") % (ip.address,
                                               self.virtual_interface_id)
            raise IpNotAllowedOnInterfaceError(err_msg)

        db.db_api.save_allowed_ip(self.id, ip.id)

    def _ip_cannot_be_allowed(self, ip):
        return (self.plugged_in_network_id() is None
                or self.plugged_in_network_id() != ip.ip_block.network_id)

    def disallow_ip(self, ip):
        db.db_api.remove_allowed_ip(interface_id=self.id, ip_address_id=ip.id)

    def ips_allowed(self):
        explicitly_allowed = db.db_query.find_allowed_ips(
            IpAddress, allowed_on_interface_id=self.id)
        allocated_ips = IpAddress.find_all_allocated_ips(interface_id=self.id)
        return list(set(allocated_ips) | set(explicitly_allowed))

    def find_allowed_ip(self, address):
        ip = utils.find(lambda ip: ip.address == address,
                        self.ips_allowed())
        if ip is None:
            raise ModelNotFoundError(
                _("Ip Address %(address)s hasnt been allowed "
                  "on interface %(vif_id)s")
                % (dict(address=address,
                        vif_id=self.virtual_interface_id)))
        return ip

    @utils.cached_property
    def network_id(self):
        return self.plugged_in_network_id()

    def plugged_in_network_id(self):
        interface_ip = IpAddress.get_by(interface_id=self.id)
        return interface_ip.ip_block.network_id if interface_ip else None

    @utils.cached_property
    def mac_address(self):
        return MacAddress.get_by(interface_id=self.id)

    @property
    def ip_addresses(self):
        return IpAddress.find_all(interface_id=self.id).all()

    @property
    def mac_address_eui_format(self):
        if self.mac_address:
            return self.mac_address.eui_format

    @property
    def mac_address_unix_format(self):
        if self.mac_address:
            return self.mac_address.unix_format

    def _validate(self):
        self._validate_presence_of("tenant_id")
        self._validate_uniqueness_of_virtual_interface_id()

    def _validate_uniqueness_of_virtual_interface_id(self):
        if self.vif_id_on_device is None:
            return
        existing_interface = self.get_by(
            vif_id_on_device=self.vif_id_on_device)
        if existing_interface and self != existing_interface:
            msg = ("Virtual Interface %s already exists")
            self._add_error('virtual_interface_id',
                            msg % self.virtual_interface_id)

    @property
    def virtual_interface_id(self):
        return self.vif_id_on_device or self.id

    @classmethod
    def delete_by(self, **kwargs):
        ifaces = Interface.find_all(**kwargs)
        for iface in ifaces:
            iface.delete()


class Policy(ModelBase):

    _data_fields = ['name', 'description', 'tenant_id']

    def _validate(self):
        self._validate_presence_of('name', 'tenant_id')

    def delete(self):
        IpRange.find_all(policy_id=self.id).delete()
        IpOctet.find_all(policy_id=self.id).delete()
        IpBlock.find_all(policy_id=self.id).update(policy_id=None)
        super(Policy, self).delete()

    def create_unusable_range(self, **attributes):
        attributes['policy_id'] = self.id
        return IpRange.create(**attributes)

    def create_unusable_ip_octet(self, **attributes):
        attributes['policy_id'] = self.id
        return IpOctet.create(**attributes)

    @utils.cached_property
    def unusable_ip_ranges(self):
        return IpRange.find_all(policy_id=self.id).all()

    @utils.cached_property
    def unusable_ip_octets(self):
        return IpOctet.find_all(policy_id=self.id).all()

    def allows(self, cidr, address):
        if any(ip_octet.applies_to(address)
               for ip_octet in self.unusable_ip_octets):
            return False
        return not any(ip_range.contains(cidr, address)
                       for ip_range in self.unusable_ip_ranges)

    def find_ip_range(self, ip_range_id):
        return IpRange.find_by(id=ip_range_id, policy_id=self.id)

    def find_ip_octet(self, ip_octet_id):
        return IpOctet.find_by(id=ip_octet_id, policy_id=self.id)

    def size(self, cidr):
        size = 0
        policies = IpRange.find_all(policy_id=self.id).all()
        policies += IpOctet.find_all(policy_id=self.id).all()
        if policies:
            for p in policies:
                size += p.size(cidr)
        return size


class IpRange(ModelBase):

    _fields_for_type_conversion = {'offset': 'integer', 'length': 'integer'}
    _data_fields = ['offset', 'length', 'policy_id']

    def contains(self, cidr, address):
        end_index = self.offset + self.length
        end_index_overshoots_length_for_negative_offset = (self.offset < 0
                                                           and end_index >= 0)
        if end_index_overshoots_length_for_negative_offset:
            end_index = None
        return (netaddr.IPAddress(address) in
                netaddr.IPNetwork(cidr)[self.offset:end_index])

    def _validate(self):
        self._validate_positive_integer('length')

    def size(self, cidr):
        block_size = netaddr.IPNetwork(cidr).size
        if self.offset >= 0:
            if (self.offset + self.length) <= block_size:
                size = self.length
            else:
                size = block_size - self.offset
        else:
            if abs(self.offset) > block_size:
                size = block_size + self.offset + self.length
            elif self.length > abs(self.offset):
                size = abs(self.offset)
            else:
                size = self.length
        return size


class IpOctet(ModelBase):

    _fields_for_type_conversion = {'octet': 'integer'}
    _data_fields = ['octet', 'policy_id']

    def applies_to(self, address):
        return self.octet == netaddr.IPAddress(address).words[-1]

    def size(size, cidr):
        cidr_prefix_length = netaddr.IPNetwork(cidr).prefixlen
        if cidr_prefix_length < 24:
            size = 2 ** (24 - cidr_prefix_length)
        else:
            size = 1
        return size


class Network(ModelBase):

    @classmethod
    def find_by(cls, id, **conditions):
        ip_blocks = IpBlock.find_all(network_id=id, **conditions).all()
        sorted_blocks = sorted(ip_blocks,
                               key=operator.attrgetter('created_at', 'id'))

        if len(sorted_blocks) == 0:
            raise ModelNotFoundError(_("Network %s not found") % id)
        return cls(id=id, ip_blocks=sorted_blocks)

    @classmethod
    def find_or_create_by(cls, id, tenant_id):
        try:
            return cls.find_by(id=id, tenant_id=tenant_id)
        except ModelNotFoundError:
            default_cidr = config.Config.get('default_cidr', None)
            if not default_cidr:
                raise ModelNotFoundError(_("Network %s not found") % id)

            ip_block = IpBlock.create(cidr=default_cidr,
                                      network_id=id,
                                      tenant_id=tenant_id,
                                      type=IpBlock.PRIVATE_TYPE)
            return cls(id=id, ip_blocks=[ip_block])

    def allocated_ips(self, interface_id):
        ips_by_block = [IpAddress.find_all(interface_id=interface_id,
                                           ip_block_id=ip_block.id).all()
                        for ip_block in self.ip_blocks]
        return [ip for sublist in ips_by_block for ip in sublist]

    def allocate_ips(self, addresses=None, **kwargs):
        if addresses:
            return filter(None, [self._allocate_specific_ip(address, **kwargs)
                                 for address in addresses])

        ips = []
        for blocks in self._block_partitions():
            for block in blocks:
                if block.max_allocation is not None:
                    if (block.ips_used >= block.max_allocation):
                        raise NetworkOverQuotaError(block.network_id)
            ips.append(self._allocate_first_free_ip(blocks, **kwargs))

        if not any(ips):
            raise exception.NoMoreAddressesError(
                _("ip blocks in network %(network-id)s are full")
                % {'network-id': self.id})

        return filter(None, ips)

    def deallocate_ips(self, interface_id):
        ips = IpAddress.find_all_by_network(self.id, interface_id=interface_id)
        for ip in ips:
            ip.deallocate()
        keep_deallocated_ips = config.Config.get(
            'keep_deallocated_ips', 'False')
        if not utils.bool_from_string(keep_deallocated_ips):
            LOG.debug("Deleting deallocated ips")
            for block in db.db_api.find_all_blocks_with_deallocated_ips():
                block.delete_deallocated_ips(deallocated_by_func=utils.utcnow)

    def find_allocated_ip(self, **conditions):
        for ip_block in self.ip_blocks:
            try:
                return IpAddress.find_by(ip_block_id=ip_block.id, **conditions)
            except ModelNotFoundError:
                pass

        raise ModelNotFoundError(_("IpAddress with %(conditions)s for "
                                   "network %(network)s not found")
                                 % (dict(conditions=conditions,
                                         network=self.id)))

    def _block_partitions(self):
        return [[block for block in self.ip_blocks
                 if not block.is_ipv6()],
                [block for block in self.ip_blocks
                 if block.is_ipv6()]]

    def _allocate_specific_ip(self, address, **kwargs):
        ip_block = utils.find(lambda ip_block: ip_block.contains(address),
                              self.ip_blocks)
        if ip_block:
            try:
                return ip_block.allocate_ip(address=address, **kwargs)
            except DuplicateAddressError:
                pass

    def _allocate_first_free_ip(self, ip_blocks, **kwargs):
        for ip_block in ip_blocks:
            if ip_block.omg_do_not_use:
                continue
            try:
                return ip_block.allocate_ip(**kwargs)
            except exception.NoMoreAddressesError:
                pass


def persisted_models():
    return {'IpBlock': IpBlock,
            'IpAddress': IpAddress,
            'Policy': Policy,
            'IpRange': IpRange,
            'IpOctet': IpOctet,
            'IpRoute': IpRoute,
            'MacAddressRange': MacAddressRange,
            'MacAddress': MacAddress,
            'Interface': Interface,
            # NOTE(jkoelker) This is here so we can slowly move off the table
            'AllocatableIp': AllocatableIp,
            }


class DuplicateAddressError(exception.MelangeError):

    message = _("Address is already allocated")


class AddressDoesNotBelongError(exception.MelangeError):

    message = _("Address does not belong here")


class AddressLockedError(exception.MelangeError):

    message = _("Address is locked")


class ModelNotFoundError(exception.MelangeError):

    message = _("Not Found")


class AddressDisallowedByPolicyError(exception.MelangeError):

    message = _("Policy does not allow this address")


class IpAllocationNotAllowedError(exception.MelangeError):

    message = _("Ip Block can not allocate address")


class IpNotAllowedOnInterfaceError(exception.MelangeError):

    message = _("Ip cannot be allowed on interface")


class InvalidModelError(exception.MelangeError):

    message = _("The following values are invalid: %(errors)s")

    def __init__(self, errors, message=None):
        super(InvalidModelError, self).__init__(message, errors=errors)


class ConcurrentAllocationError(exception.MelangeError):

    message = _("Cannot allocate resource at this time")


class NetworkOverQuotaError(exception.MelangeError):
    message = _("Too many connections on a private network")


class NoMoreMacAddressesError(exception.MelangeError):

    message = _("No more mac Addresses")


def sort(iterable):
    return sorted(iterable, key=lambda model: model.id)
