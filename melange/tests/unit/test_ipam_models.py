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

import datetime
import mox
import netaddr

from melange import tests
from melange.common import exception
from melange.common import notifier
from melange.common import utils
from melange.db import db_query
from melange.ipam import models
from melange.tests import unit
from melange.tests.factories import models as factory_models
from melange.tests.unit import mock_generator


class TestModelBase(tests.BaseTest):

    def test_create_ignores_inputs_for_auto_generated_attrs(self):
        model = factory_models.PublicIpBlockFactory(id="input_id",
                                                    created_at="input_time",
                                                    updated_at="input_time")

        self.assertNotEqual(model.id, "input_id")
        self.assertNotEqual(model.created_at, "input_time")
        self.assertNotEqual(model.updated_at, "input_time")

    def test_create_sets_timestamps(self):
        current_time = datetime.datetime(2050, 1, 1)
        with unit.StubTime(time=current_time):
            model = factory_models.PublicIpBlockFactory()

        self.assertEqual(model.created_at, current_time)
        self.assertEqual(model.updated_at, current_time)

    def test_update_ignores_inputs_for_auto_generated_attrs(self):
        model = factory_models.PublicIpBlockFactory()

        model.update(id="input_id", created_at="input_time",
                     updated_at="input_time")

        self.assertNotEqual(model.id, "input_id")
        self.assertNotEqual(model.created_at, "input_time")
        self.assertNotEqual(model.updated_at, "input_time")

    def test_update_sets_updated_at_time(self):
        model = factory_models.PublicIpBlockFactory()
        current_time = datetime.datetime(2050, 1, 1)

        with unit.StubTime(time=current_time):
            model.update(network_id="321")

        updated_model = models.IpBlock.find(model.id)
        self.assertEqual(updated_model.updated_at, current_time)

    def test_equals_is_true_when_ids_and_class_are_equal(self):
        self.assertEqual(models.ModelBase(id=1), models.ModelBase(id=1))
        self.assertEqual(models.ModelBase(id=1, name="foo"),
                         models.ModelBase(id=1, name="bar"))

    def test_equals_is_false_when_id_or_class_differ(self):
        self.assertNotEqual(models.ModelBase(), models.ModelBase())
        self.assertNotEqual(models.ModelBase(id=1), models.ModelBase(id=2))
        self.assertNotEqual(models.IpBlock(id=1), models.IpAddress(id=1))

    def test_hash_is_id_based(self):
        a = models.ModelBase(id="123", name="foo")
        b = models.ModelBase(id="123", name="bar")

        self.assertEqual(hash(a), hash(b))


class TestQuery(tests.BaseTest):

    def test_all(self):
        block1 = factory_models.IpBlockFactory(network_id="1")
        block2 = factory_models.IpBlockFactory(network_id="1")
        # Create an additional block for noise
        factory_models.IpBlockFactory(network_id="999")

        blocks = db_query.find_all(models.IpBlock, network_id="1").all()

        self.assertModelsEqual(blocks, [block1, block2])

    def test_count(self):
        factory_models.IpBlockFactory(network_id="1")
        factory_models.IpBlockFactory(network_id="1")
        # Create an additional block for noise
        factory_models.IpBlockFactory(network_id="999")

        count = db_query.find_all(models.IpBlock, network_id="1").count()

        self.assertEqual(count, 2)

    def test_query_is_iterble(self):
        block1 = factory_models.IpBlockFactory(network_id="1")
        block2 = factory_models.IpBlockFactory(network_id="1")
        # Create an additional block for noise
        factory_models.IpBlockFactory(network_id="999")

        query = db_query.find_all(models.IpBlock, network_id="1")
        blocks = [block for block in query]

        self.assertModelsEqual(blocks, [block1, block2])

    def test_limit_with_given_marker(self):
        blocks = models.sort([
            factory_models.IpBlockFactory(cidr="10.2.0.1/28"),
            factory_models.IpBlockFactory(cidr="10.3.0.1/28"),
            factory_models.IpBlockFactory(cidr="10.1.0.1/28"),
            factory_models.IpBlockFactory(cidr="10.4.0.1/28"),
        ])

        marker_block = blocks[1]
        all_blocks_query = db_query.find_all(models.IpBlock)
        paginated_blocks = all_blocks_query.limit(limit=2,
                                                  marker=marker_block.id)

        self.assertEqual(len(paginated_blocks), 2)
        self.assertEqual(paginated_blocks, [blocks[2], blocks[3]])

    def test_update(self):
        block1 = factory_models.IpBlockFactory(network_id="1")
        block2 = factory_models.IpBlockFactory(network_id="1")
        noise_block = factory_models.IpBlockFactory(network_id="999")

        db_query.find_all(models.IpBlock,
                          network_id="1").update(network_id="2")

        self.assertEqual(models.IpBlock.find(block1.id).network_id, "2")
        self.assertEqual(models.IpBlock.find(block2.id).network_id, "2")
        noise_network = models.IpBlock.find(noise_block.id).network_id
        self.assertNotEqual(noise_network, "2")

    def test_delete(self):
        block1 = factory_models.IpBlockFactory(network_id="1")
        block2 = factory_models.IpBlockFactory(network_id="1")
        noise_block = factory_models.IpBlockFactory(network_id="999")

        db_query.find_all(models.IpBlock, network_id="1").delete()

        self.assertIsNone(models.IpBlock.get(block1.id))
        self.assertIsNone(models.IpBlock.get(block2.id))
        self.assertIsNotNone(models.IpBlock.get(noise_block.id))


class TestConverter(tests.BaseTest):

    def test_converts_to_integer_value(self):
        self.assertEqual(models.Converter('integer').convert("123"), 123)
        self.assertEqual(models.Converter('integer').convert(123), 123)

    def test_converts_to_boolean_value(self):
        self.assertEqual(models.Converter('boolean').convert("True"), True)
        self.assertEqual(models.Converter('boolean').convert("False"), False)


class TestIpBlock(tests.BaseTest):

    def setUp(self):
        self.mock_generator_name = \
            "melange.tests.unit.mock_generator.MockIpV6Generator"
        super(TestIpBlock, self).setUp()

    def test_create_ip_block(self):
        factory_models.PrivateIpBlockFactory(
            cidr="10.0.0.0/8",
            network_id="18888", tenant_id='xxxx')

        saved_block = models.IpBlock.find_by(network_id="18888")
        self.assertEqual(saved_block.cidr, "10.0.0.0/8")
        self.assertEqual(saved_block.network_id, '18888')
        self.assertEqual(saved_block.type, "private")
        self.assertEqual(saved_block.tenant_id, "xxxx")

    def test_create_ip_block_with_network_name(self):
        factory_models.PrivateIpBlockFactory(
            cidr="10.0.0.0/8",
            network_id="18888", tenant_id='xxxx',
            network_name="johnnies_network")

        saved_block = models.IpBlock.find_by(network_id="18888")
        self.assertEqual(saved_block.cidr, "10.0.0.0/8")
        self.assertEqual(saved_block.network_id, '18888')
        self.assertEqual(saved_block.network_name, 'johnnies_network')
        self.assertEqual(saved_block.type, "private")
        self.assertEqual(saved_block.tenant_id, "xxxx")

    def test_block_details(self):
        v4_block = factory_models.IpBlockFactory.build(cidr="10.0.0.0/24")
        v6_block = factory_models.IpBlockFactory.build(cidr="fe::/64")

        self.assertEqual(v4_block.broadcast, "10.0.0.255")
        self.assertEqual(v4_block.netmask, "255.255.255.0")
        self.assertEqual(v6_block.broadcast, "fe::ffff:ffff:ffff:ffff")
        self.assertEqual(v6_block.netmask, "64")

    def test_length_of_block(self):
        block = factory_models.IpBlockFactory
        self.assertEqual(block(cidr="10.0.0.0/24").size(), 256)
        self.assertEqual(block(cidr="20.0.0.0/31").size(), 2)
        self.assertEqual(block(cidr="30.0.0.0/32").size(), 1)

    def test_valid_cidr(self):
        factory = factory_models.PrivateIpBlockFactory
        block = factory.build(cidr="10.1.1.1////", network_id="111")

        self.assertFalse(block.is_valid())
        self.assertEqual(block.errors, {'cidr': ["cidr is invalid"]})
        self.assertRaises(models.InvalidModelError, block.save)
        self.assertRaises(models.InvalidModelError, models.IpBlock.create,
                          cidr="10.1.0.0/33", network_id="111")

        block.cidr = "10.1.1.1/8"
        self.assertTrue(block.is_valid())

    def test_presence_of_tenant_id(self):
        factory = factory_models.PrivateIpBlockFactory
        block = factory.build(cidr="10.1.1.1/8", tenant_id=None)

        self.assertFalse(block.is_valid())
        self.assertEqual(block.errors,
                         {'tenant_id': ["tenant_id should be present"]})

    def test_validates_overlapping_cidr_for_public_ip_blocks(self):
        factory = factory_models.PublicIpBlockFactory
        factory(cidr="10.0.0.0/8", network_id="145")

        overlapping_block = factory.build(cidr="10.0.0.0/30", network_id="11")

        self.assertFalse(overlapping_block.is_valid())
        self.assertEqual(overlapping_block.errors,
                         {'cidr':
                          ["cidr overlaps with public block 10.0.0.0/8"]})

    def test_type_for_block_should_be_either_public_or_private(self):
        block = factory_models.IpBlockFactory.build(type=None,
                                                    cidr="10.0.0.0/29")

        self.assertFalse(block.is_valid())
        self.assertEqual(block.errors, {'type':
                         ["type should be one among public, private"]})

    def test_different_types_of_blocks_cannot_be_created_within_network(self):
        factory = factory_models.IpBlockFactory
        factory(network_id="1", type='private')

        block_of_different_type = factory.build(network_id="1", type='public')

        self.assertFalse(block_of_different_type.is_valid())
        self.assertEqual(block_of_different_type.errors,
                         {'type': ['type should be same within a network']})

    def test_different_types_of_blocks_can_be_created_when_no_network(self):
        private_block = factory_models.PrivateIpBlockFactory(network_id=None)
        public_block = factory_models.PublicIpBlockFactory.build(
            network_id=None)

        self.assertTrue(public_block.is_valid())
        self.assertTrue(private_block.is_valid())

    def test_save_validates_cidr_belongs_to_parent_block_cidr(self):
        factory = factory_models.PrivateIpBlockFactory
        parent_block = factory(cidr="10.0.0.0/28")
        ip_block = factory.build(cidr="10.0.0.20/29",
                                 parent_id=parent_block.id)

        self.assertFalse(ip_block.is_valid())
        self.assertEqual(ip_block.errors['cidr'],
                         ["cidr should be within parent block's cidr"])

    def test_does_not_perform_subnetting_validations_for_invalid__cidr(self):
        factory = factory_models.PrivateIpBlockFactory
        parent_block = factory(cidr="10.0.0.0/28")
        ip_block = factory.build(
            cidr="10.0.0.20////29",
            parent_id=parent_block.id)

        self.assertFalse(ip_block.is_valid())
        self.assertEqual(ip_block.errors['cidr'],
                         ["cidr is invalid"])

    def test_validates_subnet_has_same_network_as_parent(self):
        factory = factory_models.PrivateIpBlockFactory
        parent = factory(cidr="10.0.0.0/28", network_id="1")
        subnet = factory.build(cidr="10.0.0.0/29",
                               network_id="2",
                               parent_id=parent.id)

        self.assertFalse(subnet.is_valid())
        self.assertEqual(subnet.errors['network_id'],
                         ["network_id should be same as that of parent"])

    def test_subnet_fails_when_parent_block_has_allocated_ips(self):
        parent = factory_models.IpBlockFactory(cidr="10.0.0.0/24")
        _allocate_ip(parent)
        expected_msg = "parent is not subnettable since it has allocated ips"

        self.assertRaisesExcMessage(models.InvalidModelError, expected_msg,
                                    parent.subnet, cidr="10.0.0.0/30")

    def test_subnets_cidr_can_not_overlap_with_siblings(self):
        parent = factory_models.IpBlockFactory(cidr="10.0.0.0/29")
        parent.subnet(cidr="10.0.0.0/30")
        parent.subnet(cidr="10.0.0.4/30")

        factory = factory_models.IpBlockFactory
        overlapping_subnet = factory.build(cidr="10.0.0.0/31",
                                           tenant_id="2",
                                           parent_id=parent.id)

        self.assertFalse(overlapping_subnet.is_valid())
        self.assertEqual(overlapping_subnet.errors['cidr'],
                         ["cidr overlaps with sibling 10.0.0.0/30"])

    def test_cidr_can_not_overlap_with_top_level_blocks_in_the_network(self):
        factory = factory_models.IpBlockFactory
        factory(cidr="10.0.0.0/29", network_id="1")
        factory(cidr="20.0.0.0/29", network_id="1")
        overlapping_block = factory.build(cidr="10.0.0.0/31", network_id="1")

        self.assertFalse(overlapping_block.is_valid())
        self.assertEqual(
            overlapping_block.errors['cidr'],
            ["cidr overlaps with block 10.0.0.0/29 in same network"])

    def test_cidr_can_overlap_for_blocks_in_different_network(self):
        block1 = factory_models.IpBlockFactory(cidr="10.0.0.0/29",
                                               network_id="1")
        block2 = factory_models.IpBlockFactory.build(cidr="10.0.0.0/29",
                                                     network_id="2")

        self.assertTrue(block1.is_valid())
        self.assertTrue(block2.is_valid())

    def test_cidr_can_overlap_for_blocks_without_network(self):
        block1 = factory_models.IpBlockFactory(cidr="10.0.0.0/29",
                                               network_id=None)
        block2 = factory_models.IpBlockFactory.build(cidr="10.0.0.0/29",
                                                     network_id=None)

        self.assertTrue(block1.is_valid())
        self.assertTrue(block2.is_valid())

    def test_networked_top_level_blocks_have_blocks_of_different_parents(self):
        block1 = factory_models.IpBlockFactory(cidr="10.0.0.0/29",
                                               network_id=None,
                                               parent_id=None)
        subnet1 = block1.subnet(cidr="10.0.0.0/30", network_id="1")
        block2 = factory_models.IpBlockFactory(cidr="20.0.0.0/29",
                                               network_id="1")
        block3 = factory_models.IpBlockFactory(cidr="30.0.0.0/29",
                                               network_id="1")
        self.assertModelsEqual(block3.networked_top_level_blocks(),
                               [subnet1, block2])

    def test_networked_top_level_blocks_has_only_top_level_blocks(self):
        block1 = factory_models.IpBlockFactory(cidr="10.0.0.0/29",
                                               network_id="1")
        # Create a subnet in the block
        block1.subnet(cidr="10.0.0.0/30", network_id="1")
        block2 = factory_models.IpBlockFactory(cidr="20.0.0.0/29",
                                               network_id="1")
        block3 = factory_models.IpBlockFactory(cidr="30.0.0.0/29",
                                               network_id="1")

        self.assertModelsEqual(block3.networked_top_level_blocks(),
                               [block1, block2])

    def test_has_no_networked_top_level_blocks_when_not_in_network(self):
        block1 = factory_models.IpBlockFactory(cidr="10.0.0.0/29",
                                               network_id=None)
        # Create a noise block
        factory_models.IpBlockFactory(cidr="20.0.0.0/29",
                                      network_id=None)

        self.assertModelsEqual(block1.networked_top_level_blocks(), [])

    def test_subnet_creates_child_block_with_the_given_params(self):
        ip_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/28",
                                                        network_id="1",
                                                        tenant_id="2")

        subnet = ip_block.subnet("10.0.0.0/29",
                                 network_id="1",
                                 tenant_id="3")

        self.assertEqual(subnet.cidr, "10.0.0.0/29")
        self.assertEqual(subnet.network_id, "1")
        self.assertEqual(subnet.parent_id, ip_block.id)
        self.assertEqual(subnet.tenant_id, "3")
        self.assertEqual(subnet.type, ip_block.type)

    def test_subnet_derives_network_id_from_parent_block_when_not_given(self):
        ip_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/28",
                                                        network_id="2")

        subnet = ip_block.subnet("10.0.0.0/29")

        self.assertEqual(subnet.cidr, "10.0.0.0/29")
        self.assertEqual(subnet.network_id, ip_block.network_id)

    def test_subnet_derives_tenant_id_from_parent_block_when_not_given(self):
        ip_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/28",
                                                        tenant_id="2")

        subnet = ip_block.subnet("10.0.0.0/29")

        self.assertEqual(subnet.cidr, "10.0.0.0/29")
        self.assertEqual(subnet.tenant_id, ip_block.tenant_id)

    def test_save_validates_existence_parent_block_of_same_type(self):
        noise_block = factory_models.IpBlockFactory(type='public')
        block = factory_models.IpBlockFactory.build(parent_id=noise_block.id,
                                                    type='private')

        self.assertFalse(block.is_valid())
        self.assertEqual(block.errors['parent_id'],
                         ["IpBlock with type = 'private', id = '{0}' doesn't "
                          "exist".format(block.parent_id)])

    def test_save_validates_existence_policy(self):
        block = factory_models.PublicIpBlockFactory.build(
            policy_id="non-existent-id")

        self.assertFalse(block.is_valid())
        self.assertEqual(block.errors['policy_id'],
                         ["Policy with id = 'non-existent-id' doesn't exist"])

    def test_validates_gateway_is_valid_address(self):
        block = factory_models.IpBlockFactory.build(gateway="not_valid")

        self.assertFalse(block.is_valid())
        self.assertEqual(block.errors['gateway'],
                         ["Gateway is not a valid address"])

    def test_save_converts_cidr_to_lowest_address_based_on_prefix_length(self):
        block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.1/31")

        self.assertEqual(block.cidr, "10.0.0.0/31")

    def test_gateway_ip_is_not_auto_set_if_ip_block_has_only_one_ip(self):
        ipv4_block = factory_models.IpBlockFactory(cidr="10.0.0.0/32",
                                                   gateway=None)
        self.assertEqual(ipv4_block.gateway, None)

        ipv6_block = factory_models.IpBlockFactory(cidr="ff::ff/128",
                                                   gateway=None)
        self.assertEqual(ipv6_block.gateway, None)

    def test_save_sets_the_dns_values_from_conf_when_not_provided(self):
        with unit.StubConfig(dns1="ns1.example.com", dns2="ns2.example.com"):
            block = factory_models.IpBlockFactory(cidr="10.0.0.0/24",
                                                  dns1=None,
                                                  dns2=None)

        self.assertEqual(block.dns1, "ns1.example.com")
        self.assertEqual(block.dns2, "ns2.example.com")

    def test_update(self):
        block = factory_models.PublicIpBlockFactory(cidr="10.0.0.0/29",
                                                    network_id="321")

        block.update(network_id="123")

        self.assertEqual(block.network_id, "123")

    def test_update_name(self):
        block = factory_models.PublicIpBlockFactory(cidr="10.0.0.0/29",
                                                    network_id="321")

        block.update(network_name="Johnnies Network")

        self.assertEqual(block.network_name, "Johnnies Network")

    def test_find_ip_block(self):
        block1 = factory_models.PrivateIpBlockFactory(cidr="10.0.0.1/8")
        factory_models.PrivateIpBlockFactory(cidr="30.1.1.1/8")

        found_block = models.IpBlock.find(block1.id)

        self.assertEqual(found_block.cidr, block1.cidr)

    def test_find_ip_block_for_nonexistent_block(self):
        self.assertRaises(models.ModelNotFoundError,
                          models.IpBlock.find,
                          "123")

    def test_find_ip(self):
        block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.1/8")
        ip = _allocate_ip(block)
        self.assertEqual(block.find_ip(address=ip.address).id, ip.id)

    def test_percent_used(self):
        policy = factory_models.PolicyFactory(name="blah")
        factory_models.IpRangeFactory(policy_id=policy.id,
                                      offset=1,
                                      length=1)
        factory_models.IpOctetFactory(policy_id=policy.id,
                                      octet=0)
        block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.1/23",
                                                     policy_id=policy.id)
        _allocate_ip(block)
        self.assertEqual(block.percent_used, 0.78125)
        self.assertEqual(block.ips_used, 4)

    def test_find_ip_for_nonexistent_address(self):
        block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.1/8")

        self.assertRaisesExcMessage(models.ModelNotFoundError,
                                    "IpAddress Not Found",
                                    block.find_ip,
                                    address="10.0.0.1")

    def test_policy(self):
        policy = factory_models.PolicyFactory(name="Some Policy")
        ip_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/29",
                                                        policy_id=policy.id)

        self.assertEqual(ip_block.policy(), policy)

    def test_parent(self):
        parent = factory_models.IpBlockFactory()

        self.assertEqual(models.IpBlock(parent_id=parent.id).parent, parent)
        self.assertEqual(models.IpBlock(parent_id=None).parent, None)
        self.assertEqual(models.IpBlock(parent_id='non-existent').parent, None)

    def test_allocate_ip(self):
        block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/31")
        interface = factory_models.InterfaceFactory()
        ip = block.allocate_ip(interface)

        saved_ip = models.IpAddress.find(ip.id)
        self.assertEqual(ip.address, saved_ip.address)
        self.assertTrue(netaddr.IPAddress(ip.address)
                        in netaddr.IPNetwork("10.0.0.0/31"))
        self.assertEqual(ip.interface_id, interface.id)
        self.assertEqual(ip.ip_block_id, block.id)
        self.assertEqual(ip.used_by_tenant_id, interface.tenant_id)

    def test_allocate_specific_address(self):
        block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/24")
        interface = factory_models.InterfaceFactory(tenant_id="tnt_id")
        ip = block.allocate_ip(interface, address="10.0.0.2")

        expected_ip = models.IpAddress.find(ip.id)
        self.assertEqual(expected_ip.address, "10.0.0.2")
        self.assertEqual(ip.interface_id, interface.id)
        self.assertEqual(ip.ip_block_id, block.id)
        self.assertEqual(ip.used_by_tenant_id, "tnt_id")

    def skip_allocate_ip_from_non_leaf_block_fails(self):
        parent_block = factory_models.IpBlockFactory(cidr="10.0.0.0/28")
        interface = factory_models.InterfaceFactory()
        parent_block.subnet(cidr="10.0.0.0/28")
        expected_msg = "Subnetted block cannot allocate IPAddress"
        self.assertRaisesExcMessage(models.IpAllocationNotAllowedError,
                                    expected_msg,
                                    parent_block.allocate_ip,
                                    interface=interface)

    def skip_allocate_ip_from_outside_cidr(self):
        block = factory_models.PrivateIpBlockFactory(cidr="10.1.1.1/28")
        interface = factory_models.InterfaceFactory()

        self.assertRaises(models.AddressDoesNotBelongError,
                          block.allocate_ip,
                          interface=interface,
                          address="192.1.1.1")

    def test_allocating_duplicate_address_fails(self):
        interface = factory_models.InterfaceFactory()
        block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/29")
        block.allocate_ip(address='10.0.0.0', interface=interface)

        self.assertRaises(models.DuplicateAddressError,
                          block.allocate_ip,
                          interface=interface,
                          address="10.0.0.0")

    def test_allocate_ips_skips_gateway_address(self):
        interface = factory_models.InterfaceFactory()
        block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/29",
                                                     gateway="10.0.0.0")

        ip_address = block.allocate_ip(interface=interface)

        self.assertEqual(ip_address.address, "10.0.0.1")

    def test_allocate_ips_skips_broadcast_address(self):
        block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/30")
        interface = factory_models.InterfaceFactory()

        #allocate all ips except last ip(broadcast)
        for i in range(0, 3):
            block.allocate_ip(interface=interface)

        self.assertRaises(exception.NoMoreAddressesError,
                          block.allocate_ip,
                          interface=interface)

    def test_allocating_gateway_address_fails(self):
        interface = factory_models.InterfaceFactory()
        block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/29",
                                                     gateway="10.0.0.0")

        self.assertRaises(models.DuplicateAddressError,
                          block.allocate_ip,
                          interface=interface,
                          address=block.gateway)

    def test_allocating_broadcast_address_fails(self):
        interface = factory_models.InterfaceFactory()
        block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/24")

        self.assertRaises(models.DuplicateAddressError,
                          block.allocate_ip,
                          interface=interface,
                          address=block.broadcast)

    def test_allocate_ip_skips_ips_disallowed_by_policy(self):
        policy = factory_models.PolicyFactory(name="blah")
        interface = factory_models.InterfaceFactory()
        factory_models.IpRangeFactory(policy_id=policy.id,
                                      offset=1,
                                      length=1)
        block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/29",
                                                     policy_id=policy.id)

        self.assertEqual(block.allocate_ip(interface).address, "10.0.0.0")
        self.assertEqual(block.allocate_ip(interface).address, "10.0.0.2")

    def test_allocating_ip_fails_due_to_policy(self):
        policy = factory_models.PolicyFactory(name="blah")
        interface = factory_models.InterfaceFactory()
        factory_models.IpRangeFactory(policy_id=policy.id,
                                      offset=0,
                                      length=1)
        block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/29",
                                                     policy_id=policy.id)

        self.assertRaises(models.AddressDisallowedByPolicyError,
                          block.allocate_ip,
                          interface=interface,
                          address="10.0.0.0")

    def test_ip_block_is_marked_full_when_all_ips_are_allocated(self):
        interface = factory_models.InterfaceFactory()
        ip_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/30")

        for i in range(0, 3):
            ip_block.allocate_ip(interface=interface)

        self.assertRaises(exception.NoMoreAddressesError,
                          ip_block.allocate_ip,
                          interface=interface)
        self.assertTrue(ip_block.is_full)

    def test_allocate_ip_raises_error_when_ip_block_is_marked_full(self):
        interface = factory_models.InterfaceFactory()
        ip_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/29",
                                                        is_full=True)

        self.assertRaises(exception.NoMoreAddressesError,
                          ip_block.allocate_ip,
                          interface=interface)

    def test_allocate_ip_fails_when_iface_configured_for_other_net_ip(self):
        iface_with_net1 = factory_models.InterfaceFactory()
        net1_block = factory_models.IpBlockFactory(network_id="1")
        net1_block.allocate_ip(iface_with_net1)
        net2_block = factory_models.IpBlockFactory(network_id="2")

        expected_error_msg = ("Interface %s is configured on another network"
                              % iface_with_net1.vif_id_on_device)

        self.assertRaisesExcMessage(models.IpAllocationNotAllowedError,
                                    expected_error_msg,
                                    net2_block.allocate_ip,
                                    iface_with_net1)

    def test_allocate_ip_retries_on_ip_creation_constraint_failure(self):
        interface = factory_models.InterfaceFactory()
        ip_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/24")
        no_of_retries = 3

        self.mock.StubOutWithMock(models.IpAddress, 'allocate')
        for i in range(no_of_retries - 1):
            self._mock_ip_allocate().AndRaise(exception.DBConstraintError())
        expected_ip = models.IpAddress(id=1, address="10.0.0.2")
        self._mock_ip_allocate().AndReturn(expected_ip)
        self.mock.ReplayAll()

        with unit.StubConfig(ip_allocation_retries=no_of_retries):
            actual_ip = ip_block.allocate_ip(interface)

        self.assertEqual(actual_ip, expected_ip)

    def test_allocate_ip_raises_error_after_max_retries(self):
        interface = factory_models.InterfaceFactory()
        ip_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/24")
        no_of_retries = 3

        self.mock.StubOutWithMock(models.IpAddress, 'allocate')

        for i in range(no_of_retries):
            self._mock_ip_allocate().AndRaise(exception.DBConstraintError())

        self.mock.ReplayAll()

        expected_error_msg = ("Cannot allocate address for block {0} "
                              "at this time".format(ip_block.id))
        expected_exception = models.ConcurrentAllocationError
        with unit.StubConfig(ip_allocation_retries=no_of_retries):
            self.assertRaisesExcMessage(expected_exception,
                                        expected_error_msg,
                                        ip_block.allocate_ip,
                                        interface=interface)

    def _mock_ip_allocate(self):
        return models.IpAddress.allocate(ip_block=mox.IgnoreArg(),
                                         interface=mox.IgnoreArg())

    def _mock_ip_creation(self):
        return models.IpAddress.create(address=mox.IgnoreArg(),
                                       interface_id=mox.IgnoreArg(),
                                       used_by_tenant_id=mox.IgnoreArg(),
                                       ip_block_id=mox.IgnoreArg())

    def test_ip_block_is_not_full(self):
        ip_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/28")
        self.assertFalse(ip_block.is_full)

    def test_allocate_ip_when_no_more_ips_raises_no_more_addresses_error(self):
        block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/30")
        interface = factory_models.InterfaceFactory()

        for i in range(0, 3):
            block.allocate_ip(interface=interface)

        self.assertRaises(exception.NoMoreAddressesError,
                          block.allocate_ip,
                          interface=interface)

    def test_allocate_ip_is_not_duplicated(self):
        block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/30")
        interface = factory_models.InterfaceFactory()

        self.assertEqual(block.allocate_ip(interface).address, "10.0.0.0")
        self.assertEqual(block.allocate_ip(interface).address, "10.0.0.1")

    def test_allocate_ip_for_ipv6_block_uses_pluggable_algo(self):
        block = factory_models.IpV6IpBlockFactory(cidr="ff::/120")
        interface = factory_models.InterfaceFactory()
        mock_generator.MockIpV6Generator.ip_list = ["ff::0001", "ff::0002"]

        with unit.StubConfig(ipv6_generator=self.mock_generator_name):
            ip = block.allocate_ip(interface=interface)

        self.assertEqual(ip.address, "00ff:0000:0000:0000:0000:0000:0000:0001")

    def test_allocate_ip_for_ipv6_block_iterates_till_free_ip_is_found(self):
        block = factory_models.IpV6IpBlockFactory(cidr="ff::/120")
        interface = factory_models.InterfaceFactory()
        mock_generator.MockIpV6Generator.ip_list = ["ff::0001", "ff::0002"]
        factory_models.IpAddressFactory(address="ff::0001",
                                        ip_block_id=block.id)

        with unit.StubConfig(ipv6_generator=self.mock_generator_name):
            ip = block.allocate_ip(interface=interface)

        self.assertEqual(ip.address, "00ff:0000:0000:0000:0000:0000:0000:0002")

    def test_allocate_ip_for_given_ipv6_address(self):
        block = factory_models.IpV6IpBlockFactory(cidr="ff::/120")
        interface = factory_models.InterfaceFactory()

        ip = block.allocate_ip(interface=interface, address="ff::2")

        self.assertEqual(ip.address, "00ff:0000:0000:0000:0000:0000:0000:0002")

    def test_allocate_ip_fails_if_given_ipv6_address_already_exists(self):
        interface = factory_models.InterfaceFactory()
        block = factory_models.IpV6IpBlockFactory(cidr="ff::/120")
        factory_models.IpAddressFactory(address="ff::2",
                                        ip_block_id=block.id)

        self.assertRaises(models.DuplicateAddressError,
                          block.allocate_ip,
                          interface=interface,
                          address="ff::2")

    def test_allocate_ip_fails_if_given_ipv6_address_outside_block_cidr(self):
        interface = factory_models.InterfaceFactory()
        block = factory_models.IpV6IpBlockFactory(cidr="ff::/120")

        self.assertRaises(models.AddressDoesNotBelongError,
                          block.allocate_ip,
                          interface=interface,
                          address="fe::2")

    def test_find_allocated_ip(self):
        block = factory_models.PrivateIpBlockFactory()
        actual_ip = _allocate_ip(block)

        expected_ip = models.IpBlock.find_allocated_ip(
            block.id, block.tenant_id, address=actual_ip.address)

        self.assertEqual(expected_ip, actual_ip)

    def test_find_allocated_ip_raises_locked_error_for_deallocated_ips(self):
        block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/30")
        ip = _allocate_ip(block)

        ip.deallocate()

        self.assertRaises(models.AddressLockedError,
                          models.IpBlock.find_allocated_ip,
                          block.id,
                          block.tenant_id,
                          address=ip.address)

    def test_find_allocated_ip_when_ip_block_not_belongs_to_tenant(self):
        block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/30")
        ip = _allocate_ip(block)

        self.assertRaises(models.ModelNotFoundError,
                          models.IpBlock.find_allocated_ip,
                          block.id,
                          "wrong_tenant_id",
                          address=ip.address)

    def test_deallocate_ip(self):
        interface = factory_models.InterfaceFactory()
        block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/24")
        ip = _allocate_ip(block)

        block.deallocate_ip(ip.address)

        self.assertRaises(models.AddressLockedError,
                          models.IpBlock.find_allocated_ip,
                          block.id,
                          block.tenant_id,
                          address=ip.address)

        self.assertRaises(models.DuplicateAddressError,
                          block.allocate_ip,
                          address=ip.address,
                          interface=interface)

    def test_data_with_gateway(self):
        policy = factory_models.PolicyFactory()
        parent_block = factory_models.PrivateIpBlockFactory(
            cidr="10.0.0.0/24")
        ip_block = factory_models.PrivateIpBlockFactory(
            cidr="10.0.0.0/29",
            policy_id=policy.id,
            parent_id=parent_block.id,
            gateway="10.0.0.1")
        data = ip_block.data()

        self.assertEqual(data['id'], ip_block.id)
        self.assertEqual(data['cidr'], ip_block.cidr)
        self.assertEqual(data['network_id'], ip_block.network_id)
        self.assertEqual(data['tenant_id'], ip_block.tenant_id)
        self.assertEqual(data['policy_id'], ip_block.policy_id)
        self.assertEqual(data['parent_id'], ip_block.parent_id)
        self.assertEqual(data['created_at'], ip_block.created_at)
        self.assertEqual(data['updated_at'], ip_block.updated_at)
        self.assertEqual(data['broadcast'], "10.0.0.7")
        self.assertEqual(data['gateway'], "10.0.0.1")
        self.assertEqual(data['netmask'], "255.255.255.248")
        self.assertEqual(data['dns1'], ip_block.dns1)
        self.assertEqual(data['dns2'], ip_block.dns2)

    def test_data_without_gateway(self):
        policy = factory_models.PolicyFactory()
        parent_block = factory_models.PrivateIpBlockFactory(
            cidr="10.0.0.0/24")
        ip_block = factory_models.PrivateIpBlockFactory(
            cidr="10.0.0.0/29",
            policy_id=policy.id,
            parent_id=parent_block.id)
        data = ip_block.data()

        self.assertEqual(data['id'], ip_block.id)
        self.assertEqual(data['cidr'], ip_block.cidr)
        self.assertEqual(data['network_id'], ip_block.network_id)
        self.assertEqual(data['tenant_id'], ip_block.tenant_id)
        self.assertEqual(data['policy_id'], ip_block.policy_id)
        self.assertEqual(data['parent_id'], ip_block.parent_id)
        self.assertEqual(data['created_at'], ip_block.created_at)
        self.assertEqual(data['updated_at'], ip_block.updated_at)
        self.assertEqual(data['broadcast'], "10.0.0.7")
        self.assertEqual(data['gateway'], None)
        self.assertEqual(data['netmask'], "255.255.255.248")
        self.assertEqual(data['dns1'], ip_block.dns1)
        self.assertEqual(data['dns2'], ip_block.dns2)

    def test_find_all_ip_blocks(self):
        factory_models.PrivateIpBlockFactory(cidr="10.2.0.0/28")
        factory_models.PrivateIpBlockFactory(cidr="10.3.0.0/28")
        factory_models.PrivateIpBlockFactory(cidr="10.1.0.0/28")

        blocks = models.IpBlock.find_all().all()

        self.assertEqual(len(blocks), 3)
        self.assertItemsEqual(["10.2.0.0/28", "10.3.0.0/28", "10.1.0.0/28"],
                              [block.cidr for block in blocks])

    def test_delete(self):
        ip_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/29")
        ip_block.delete()
        self.assertTrue(models.IpBlock.get(ip_block.id) is None)

    def test_delete_to_cascade_delete_ip_addresses(self):
        ip_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/29")
        factory_models.IpAddressFactory(ip_block_id=ip_block.id,
                                        address="10.0.0.0")
        factory_models.IpAddressFactory(ip_block_id=ip_block.id,
                                        address="10.0.0.1")

        ip_block.delete()
        ips = models.IpAddress.find_all(ip_block_id=ip_block.id).all()
        self.assertTrue(len(ips) is 0)

    def test_delete_to_cascade_delete_subnet_tree_and_their_address(self):
        ip_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/29")
        subnet1 = ip_block.subnet("10.0.0.0/30")
        subnet11 = subnet1.subnet("10.0.0.1/31")
        subnet2 = ip_block.subnet("10.0.0.4/30")
        ip1 = factory_models.IpAddressFactory(ip_block_id=subnet11.id,
                                              address="10.0.0.0")
        ip2 = factory_models.IpAddressFactory(ip_block_id=subnet2.id,
                                              address="10.0.0.4")

        ip_block.delete()

        self.assertIsNone(models.IpBlock.get(subnet1.id))
        self.assertIsNone(models.IpBlock.get(subnet11.id))
        self.assertIsNone(models.IpBlock.get(subnet2.id))
        self.assertIsNone(models.IpAddress.get(ip1.id))
        self.assertIsNone(models.IpAddress.get(ip2.id))

    def test_contains_address(self):
        ip_block = models.IpBlock(cidr="10.0.0.0/20")

        self.assertTrue(ip_block.contains("10.0.0.232"))
        self.assertFalse(ip_block.contains("20.0.0.232"))

    def test_is_ipv6(self):
        ip_block = models.IpBlock(cidr="ff::/120")

        self.assertTrue(ip_block.is_ipv6())

    def test_subnets(self):
        ip_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/28")
        subnet1 = factory_models.PrivateIpBlockFactory(
            cidr="10.0.0.0/29",
            parent_id=ip_block.id)
        subnet2 = factory_models.PrivateIpBlockFactory(
            cidr="10.0.0.8/29",
            parent_id=ip_block.id)

        self.assertModelsEqual(ip_block.subnets(), [subnet1, subnet2])

    def test_siblings_of_non_root_node(self):
        ip_block = factory_models.IpBlockFactory(cidr="10.0.0.0/28")

        subnet1 = ip_block.subnet("10.0.0.0/29")
        subnet2 = ip_block.subnet("10.0.0.8/30")
        subnet3 = ip_block.subnet("10.0.0.12/30")
        subnet11 = subnet1.subnet("10.0.0.0/30")

        self.assertModelsEqual(subnet2.siblings(), [subnet1, subnet3])
        self.assertModelsEqual(subnet11.siblings(), [])

    def test_siblings_of_root_node_is_empty(self):
        ip_block = factory_models.IpBlockFactory(cidr="10.0.0.0/28")

        self.assertModelsEqual(ip_block.siblings(), [])

    def test_delete_all_deallocated_ips_after_default_of_two_days(self):
        ip_block1 = factory_models.PrivateIpBlockFactory(cidr="10.0.1.1/24")
        ip_block2 = factory_models.PrivateIpBlockFactory(cidr="20.0.1.1/24")
        current_time = datetime.datetime(2050, 1, 1)
        two_days_before = current_time - datetime.timedelta(days=2)
        ip1 = _allocate_ip(ip_block1)
        ip2 = _allocate_ip(ip_block2)
        with unit.StubTime(time=two_days_before):
            ip1.deallocate()
            ip2.deallocate()

        with unit.StubTime(time=current_time):
            models.IpBlock.delete_all_deallocated_ips(
                deallocated_by_func=models.deallocated_by_date)

        self.assertEqual(ip_block1.addresses(), [])
        self.assertEqual(ip_block2.addresses(), [])

    def test_delete_deallocated_ips_immediately(self):
        ip_block = factory_models.PrivateIpBlockFactory(cidr="10.0.1.1/24")
        current_time = datetime.datetime(2050, 1, 1)
        ip1 = _allocate_ip(ip_block)
        ip2 = _allocate_ip(ip_block)
        ip3 = _allocate_ip(ip_block)
        with unit.StubTime(time=current_time):
            ip1.deallocate()
            ip3.deallocate()

        with unit.StubTime(time=current_time):
            ip_block.delete_deallocated_ips(deallocated_by_func=utils.utcnow)

        self.assertModelsEqual(ip_block.addresses(), [ip2])

    def test_delete_deallocated_ips_after_default_of_two_days(self):
        ip_block = factory_models.PrivateIpBlockFactory(cidr="10.0.1.1/24")
        current_time = datetime.datetime(2050, 1, 1)
        two_days_before = current_time - datetime.timedelta(days=2)
        ip1 = _allocate_ip(ip_block)
        ip2 = _allocate_ip(ip_block)
        ip3 = _allocate_ip(ip_block)
        with unit.StubTime(time=two_days_before):
            ip1.deallocate()
            ip3.deallocate()

        with unit.StubTime(time=current_time):
            ip_block.delete_deallocated_ips(
                deallocated_by_func=models.deallocated_by_date)

        self.assertModelsEqual(ip_block.addresses(), [ip2])

    def test_delete_deallocated_ips_after_configured_no_of_days(self):
        ip_block = factory_models.PrivateIpBlockFactory(cidr="10.0.1.1/24")
        ip1 = _allocate_ip(ip_block)
        ip2 = _allocate_ip(ip_block)
        ip3 = _allocate_ip(ip_block)
        ip4 = _allocate_ip(ip_block)
        current_time = datetime.datetime(2050, 1, 1)
        one_day_before = current_time - datetime.timedelta(days=1)
        two_days_before = current_time - datetime.timedelta(days=2)
        with unit.StubTime(time=two_days_before):
            ip1.deallocate()
            ip3.deallocate()
        with unit.StubTime(time=one_day_before):
            ip4.deallocate()
        with unit.StubTime(time=current_time):
            ip2.deallocate()

        with unit.StubConfig(keep_deallocated_ips_for_days=1):
            with unit.StubTime(time=current_time):
                ip_block.delete_deallocated_ips(
                    deallocated_by_func=models.deallocated_by_date)

        self.assertEqual(ip_block.addresses(), [ip2])

    def test_is_full_flag_reset_when_addresses_are_deleted(self):
        interface = factory_models.InterfaceFactory()
        ip_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.0/30")

        for i in range(0, 2):
            _allocate_ip(ip_block, interface=interface)

        ip = _allocate_ip(ip_block, interface=interface)

        self.assertRaises(exception.NoMoreAddressesError,
                          ip_block.allocate_ip,
                          interface=interface)
        self.assertTrue(ip_block.is_full)

        ip.deallocate()

        models.IpBlock.delete_all_deallocated_ips(
            deallocated_by_func=models.deallocated_by_date)

        self.assertFalse(models.IpBlock.find(ip_block.id).is_full)

    def test_ip_routes(self):
        block1 = factory_models.IpBlockFactory()
        block2 = factory_models.IpBlockFactory()

        ip_routes = [factory_models.IpRouteFactory(source_block_id=block1.id),
                     factory_models.IpRouteFactory(source_block_id=block1.id)]
        # Create a noise route
        factory_models.IpRouteFactory(source_block_id=block2.id)

        self.assertModelsEqual(block1.ip_routes(), ip_routes)

    def test_ip_block_creation_is_notified(self):
        self.setup_uuid_with("ip_block_uuid")
        creation_time = datetime.datetime(2050, 1, 1)
        mock_notifier = _setup_notifier(self.mock)
        mock_notifier.info("create IpBlock", dict(tenant_id="tnt_id",
                                                  id="ip_block_uuid",
                                                  type="private",
                                                  created_at=creation_time))
        self.mock.ReplayAll()

        with unit.StubTime(time=creation_time):
            factory_models.IpBlockFactory(tenant_id="tnt_id",
                                          type="private",)

    def test_ip_block_deletion_is_notified(self):
        block = factory_models.IpBlockFactory(tenant_id="tnt_id",
                                              type="private")
        mock_notifier = _setup_notifier(self.mock)
        mock_notifier.info("delete IpBlock", dict(tenant_id="tnt_id",
                                                  type=block.type,
                                                  id=block.id,
                                                  created_at=block.created_at))
        self.mock.ReplayAll()

        block.delete()

    def test_no_ips_allocated(self):
        empty_block = factory_models.IpBlockFactory()
        block = factory_models.IpBlockFactory()
        block.allocate_ip(factory_models.InterfaceFactory())

        self.assertTrue(empty_block.no_ips_allocated())
        self.assertFalse(block.no_ips_allocated())


class TestIpAddress(tests.BaseTest):

    def test_str_returns_address(self):
        self.assertEqual(str(models.IpAddress(address="10.0.1.1")), "10.0.1.1")

    def test_address_for_a_ip_block_is_unique(self):
        block1 = factory_models.PrivateIpBlockFactory(cidr="10.1.1.1/24")
        block2 = factory_models.PrivateIpBlockFactory(cidr="20.1.1.1/24")
        block1_ip = factory_models.IpAddressFactory(address="10.1.1.3",
                                                    ip_block_id=block1.id)
        interface = factory_models.InterfaceFactory()

        expected_error = ("Failed to save IpAddress")
        self.assertRaisesExcMessage(exception.DBConstraintError,
                                    expected_error,
                                    models.IpAddress.create,
                                    ip_block_id=block1.id,
                                    address=block1_ip.address,
                                    used_by_tenant_id="tnt_id",
                                    interface_id=interface.id)

        self.assertIsNotNone(models.IpAddress.create(ip_block_id=block2.id,
                             address=block1_ip.address,
                             used_by_tenant_id="tnt_id",
                             interface_id=interface.id))

    def test_find_ip_address(self):
        block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.1/8")
        ip_address = factory_models.IpAddressFactory(ip_block_id=block.id,
                                                     address="10.0.0.1")

        self.assertNotEqual(models.IpAddress.find(ip_address.id), None)

    def test_find_ips_in_network(self):
        ip_block1 = factory_models.IpBlockFactory(network_id="1")
        ip_block2 = factory_models.IpBlockFactory(network_id="1")
        noise_block = factory_models.IpBlockFactory(network_id="999")
        # Create a noise IP
        _allocate_ip(noise_block)
        ips = [_allocate_ip(block) for block in [ip_block1, ip_block2]]

        self.assertModelsEqual(models.IpAddress.find_all_by_network("1"), ips)

    def test_ipv6_address_is_expanded_before_save(self):
        ip_address = factory_models.IpAddressFactory(address="fe:0:1::2")

        self.assertEqual(ip_address.address,
                         "00fe:0000:0001:0000:0000:0000:0000:0002")

    def test_ipv4_address_is_formatted_before_save(self):
        ip_address = factory_models.IpAddressFactory(address="10.11.003.255")

        self.assertEqual(ip_address.address, "10.11.3.255")

    def test_find_ip_address_for_nonexistent_address(self):
        self.assertRaises(models.ModelNotFoundError,
                          models.IpAddress.find,
                          "123")

    def test_find_all_allocated_ips(self):
        block1 = factory_models.IpBlockFactory(tenant_id="1")
        block2 = factory_models.IpBlockFactory(tenant_id="1")
        interface1 = factory_models.InterfaceFactory()
        interface2 = factory_models.InterfaceFactory()

        ip1 = _allocate_ip(block1, interface=interface1)
        ip2 = _allocate_ip(block1, interface=interface1)
        ip3 = _allocate_ip(block1, interface=interface1)
        block2_ip = _allocate_ip(block2, interface=interface1)
        # Create a noise IP
        _allocate_ip(block1, interface=interface2)

        ip2.deallocate()

        allocated_ips = models.IpAddress.find_all_allocated_ips(
            interface_id=interface1.id)
        self.assertModelsEqual(allocated_ips, [ip1, ip3, block2_ip])

    def test_delete_ip_address(self):
        block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.1/8")
        ip = factory_models.IpAddressFactory(ip_block_id=block.id,
                                             address="10.0.0.1")

        ip.delete()

        self.assertIsNone(models.IpAddress.get(ip.id))

    def test_add_inside_locals(self):
        global_ip = factory_models.IpAddressFactory()
        local_ip = factory_models.IpAddressFactory()

        global_ip.add_inside_locals([local_ip])

        self.assertTrue(global_ip.id in [ip.id for ip
                                         in local_ip.inside_globals()])

    def test_add_inside_globals(self):
        global_ip = factory_models.IpAddressFactory()
        local_ip = factory_models.IpAddressFactory()

        local_ip.add_inside_globals([global_ip])

        self.assertTrue(local_ip.id in [ip.id for ip in
                                        global_ip.inside_locals()])

    def test_limited_show_inside_locals(self):
        global_block = factory_models.PrivateIpBlockFactory(cidr="192.0.0.1/8")
        local_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.1/8")
        global_ip = _allocate_ip(global_block)
        local_ips = models.sort([_allocate_ip(local_block) for i in range(5)])
        global_ip.add_inside_locals(local_ips)

        inside_locals_query = global_ip.inside_locals()
        expected_locals, next_mrk = inside_locals_query.paginated_collection(
            limit=2, marker=local_ips[1].id)

        self.assertModelsEqual(expected_locals, [local_ips[2], local_ips[3]])

    def test_limited_show_inside_globals(self):
        global_block = factory_models.PrivateIpBlockFactory(cidr="192.0.0.1/8")
        local_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.1/8")
        global_ips = models.sort([_allocate_ip(global_block)
                                  for i in range(5)])
        local_ip = _allocate_ip(local_block)
        local_ip.add_inside_globals(global_ips)

        inside_globals_query = local_ip.inside_globals()
        inside_globals, next_mrk = inside_globals_query.paginated_collection(
            limit=2, marker=global_ips[1].id)

        self.assertModelsEqual(inside_globals, [global_ips[2], global_ips[3]])
        self.assertEqual(next_mrk, global_ips[3].id)

    def test_remove_inside_globals(self):
        global_block = factory_models.PrivateIpBlockFactory(cidr="192.0.0.1/8")
        local_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.1/8")

        global_ips = [_allocate_ip(global_block) for i in range(5)]
        local_ip = _allocate_ip(local_block)
        local_ip.add_inside_globals(global_ips)

        local_ip.remove_inside_globals()

        self.assertEqual(local_ip.inside_globals().all(), [])

    def test_remove_inside_globals_for_specific_address(self):
        global_block = factory_models.PrivateIpBlockFactory(cidr="192.0.0.1/8")
        local_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.1/8")

        global_ips = [_allocate_ip(global_block) for i in range(5)]
        local_ip = _allocate_ip(local_block)
        local_ip.add_inside_globals(global_ips)

        local_ip.remove_inside_globals(global_ips[0].address)

        globals_left = [ip.address for ip in local_ip.inside_globals()]
        self.assertItemsEqual(globals_left,
                              [ip.address for ip in global_ips[1:5]])

    def test_remove_inside_locals_for_specific_address(self):
        global_block = factory_models.PrivateIpBlockFactory(cidr="192.0.0.1/8")
        local_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.1/8")

        global_ip = _allocate_ip(global_block)
        local_ips = [_allocate_ip(local_block) for i in range(5)]
        global_ip.add_inside_locals(local_ips)
        global_ip.remove_inside_locals(local_ips[0].address)

        locals_left = [ip.address for ip in global_ip.inside_locals()]
        self.assertItemsEqual(locals_left,
                              [ip.address for ip in local_ips[1:5]])

    def test_remove_inside_locals(self):
        global_block = factory_models.PrivateIpBlockFactory(cidr="192.0.0.1/8")
        local_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.1/8")

        local_ips = [_allocate_ip(local_block) for i in range(5)]
        global_ip = _allocate_ip(global_block)
        global_ip.add_inside_locals(local_ips)

        global_ip.remove_inside_locals()

        self.assertEqual(global_ip.inside_locals().all(), [])

    def test_data(self):
        ip_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.1/8")
        interface = factory_models.InterfaceFactory()
        ip = factory_models.IpAddressFactory(ip_block_id=ip_block.id,
                                             interface_id=interface.id)

        data = ip.data()

        self.assertEqual(data['id'], ip.id)
        self.assertEqual(data['ip_block_id'], ip.ip_block_id)
        self.assertEqual(data['address'], ip.address)
        self.assertEqual(data['version'], ip.version)
        self.assertEqual(data['used_by_tenant'], interface.tenant_id)
        self.assertEqual(data['used_by_device'], interface.device_id)
        self.assertEqual(data['interface_id'], interface.vif_id_on_device)
        self.assertEqual(data['created_at'], ip.created_at)
        self.assertEqual(data['updated_at'], ip.updated_at)

    def test_deallocate(self):
        ip_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.1/8")
        ip_address = _allocate_ip(ip_block)
        current_time = datetime.datetime(2050, 1, 1)

        with unit.StubTime(time=current_time):
            ip_address.deallocate()

        self.assertNotEqual(models.IpAddress.find(ip_address.id), None)

        deallocated_address = models.IpAddress.find(ip_address.id)
        self.assertTrue(deallocated_address.marked_for_deallocation)
        self.assertTrue(deallocated_address.deallocated_at, current_time)

    def test_restore(self):
        ip_block = factory_models.PrivateIpBlockFactory(cidr="10.0.0.1/24")
        ip_address = _allocate_ip(ip_block)
        ip_address.deallocate()

        ip_address.restore()

        self.assertFalse(ip_address.marked_for_deallocation)
        self.assertIsNone(ip_address.deallocated_at)

    def test_ip_block(self):
        ip_block = factory_models.PrivateIpBlockFactory()
        ip_address = factory_models.IpAddressFactory(ip_block_id=ip_block.id)

        self.assertEqual(ip_address.ip_block, ip_block)

    def test_find_by_takes_care_of_expanding_ipv6_addresses(self):
        actual_ip = factory_models.IpAddressFactory(address="00fe:0:0001::2")
        # Create a noise ip
        factory_models.IpAddressFactory(address="fe00:0:0001::2")

        found_ip = models.IpAddress.find_by(address="fe:0:1::2")

        self.assertEqual(actual_ip, found_ip)

    def test_find_all_takes_care_of_expanding_ipv6_addresses(self):
        actual_ip = factory_models.IpAddressFactory(address="00fe:0:0001::2")
        # Create a noise ip
        factory_models.IpAddressFactory(address="fe00:0:0001::2")

        found_ips = models.IpAddress.find_all(address="fe:0:1::2").all()

        self.assertEqual([actual_ip], found_ips)

    def test_version_of_ip(self):
        ipv4 = factory_models.IpAddressFactory(address="10.1.1.1")
        ipv6 = factory_models.IpAddressFactory(address="fe::1")

        self.assertEqual(ipv4.version, 4)
        self.assertEqual(ipv6.version, 6)

    def test_retrieves_interface(self):
        interface = factory_models.InterfaceFactory(vif_id_on_device="112")
        ip = factory_models.IpAddressFactory(interface_id=interface.id)

        self.assertEqual(ip.interface, interface)
        self.assertEqual(ip.interface.virtual_interface_id, "112")

    def test_vif_id_on_device(self):
        interface = factory_models.InterfaceFactory(vif_id_on_device="112")
        ip = factory_models.IpAddressFactory(interface_id=interface.id)

        self.assertEqual(ip.virtual_interface_id, "112")

    def test_mac_address(self):
        mac_range = factory_models.MacAddressRangeFactory()
        interface = factory_models.InterfaceFactory()
        mac_address = mac_range.allocate_mac(interface_id=interface.id)
        ip = factory_models.IpAddressFactory(interface_id=interface.id)

        self.assertEqual(ip.mac_address, mac_address)

    def test_validates_existance_of_interface(self):
        ip = factory_models.IpAddressFactory.build(interface_id="bad_id")
        self.assertFalse(ip.is_valid())
        self.assertEqual(ip.errors['interface_id'],
                         ["Interface with id = 'bad_id' doesn't exist"])

    def test_validates_presence_of_used_by_tenant(self):
        ip = factory_models.IpAddressFactory.build(used_by_tenant_id=None)
        self.assertFalse(ip.is_valid())
        self.assertEqual(ip.errors['used_by_tenant_id'],
                         ["used_by_tenant_id should be present"])

    def test_ip_addresss_creation_is_notified(self):
        block = factory_models.IpBlockFactory(cidr="10.1.1.1/24")
        self.setup_uuid_with("ip_address_uuid")
        creation_time = datetime.datetime(2050, 1, 1)
        mock_notifier = _setup_notifier(self.mock)
        mock_notifier.info("create IpAddress", dict(used_by_tenant_id="tnt_id",
                                                    id="ip_address_uuid",
                                                    address="10.1.1.1",
                                                    used_by_device_id="ins",
                                                    ip_block_id=block.id,
                                                    created_at=creation_time))
        self.mock.ReplayAll()

        with unit.StubTime(time=creation_time):
            interface = factory_models.InterfaceFactory(device_id="ins")
            factory_models.IpAddressFactory(used_by_tenant_id="tnt_id",
                                            address="10.1.1.1",
                                            ip_block_id=block.id,
                                            interface_id=interface.id)

    def test_ip_addresss_delete_is_notified(self):
        block = factory_models.IpBlockFactory(cidr="10.1.1.1/24")
        interface = factory_models.InterfaceFactory(device_id="ins")
        ip = factory_models.IpAddressFactory(used_by_tenant_id="tnt_id",
                                             address="10.1.1.1",
                                             ip_block_id=block.id,
                                             interface_id=interface.id,
                                             )

        mock_notifier = _setup_notifier(self.mock)
        mock_notifier.info("delete IpAddress", dict(used_by_tenant_id="tnt_id",
                                                    id=ip.id,
                                                    address=ip.address,
                                                    used_by_device_id="ins",
                                                    ip_block_id=block.id,
                                                    created_at=ip.created_at))
        self.mock.ReplayAll()

        ip.delete()


class TestIpRoute(tests.BaseTest):

    def test_create(self):
        block = factory_models.IpBlockFactory()

        models.IpRoute.create(source_block_id=block.id,
                              destination="10.0.0.0",
                              netmask="255.255.192.0",
                              gateway="192.168.0.1")

        created_route = models.IpRoute.find_by(source_block_id=block.id)

        self.assertIsNotNone(created_route)
        self.assertEqual(created_route.destination, "10.0.0.0")
        self.assertEqual(created_route.netmask, "255.255.192.0")
        self.assertEqual(created_route.gateway, "192.168.0.1")

    def test_presence_of_destination(self):
        ip_route = factory_models.IpRouteFactory.build(destination=None)

        self.assertFalse(ip_route.is_valid())
        self.assertEqual(ip_route.errors['destination'],
                         ["destination should be present"])

    def test_presence_of_gateway(self):
        ip_route = factory_models.IpRouteFactory.build(gateway=None)

        self.assertFalse(ip_route.is_valid())
        self.assertEqual(ip_route.errors['gateway'],
                         ["gateway should be present"])

    def test_existence_of_source_block(self):
        factory = factory_models.IpRouteFactory
        ip_route = factory.build(source_block_id="invalid")

        self.assertFalse(ip_route.is_valid())
        self.assertEqual(ip_route.errors['source_block_id'],
                         ["IpBlock with id = 'invalid' doesn't exist"])

    def test_data(self):
        ip_route = factory_models.IpRouteFactory()

        data = ip_route.data()
        self.assertEqual(data["destination"], ip_route.destination)
        self.assertEqual(data["netmask"], ip_route.netmask)
        self.assertEqual(data["gateway"], ip_route.gateway)


class TestMacAddressRange(tests.BaseTest):

    def test_allocate_mac_address(self):
        mac_address_range = factory_models.MacAddressRangeFactory(
            cidr="BC:76:4E:20:00:00/27")

        mac_address = mac_address_range.allocate_mac()

        self.assertEqual(netaddr.EUI(mac_address.address),
                         netaddr.EUI("BC:76:4E:20:00:00"))

        saved_mac = models.MacAddress.get(mac_address.id)
        self.assertIsNotNone(saved_mac)
        self.assertEqual(saved_mac.mac_address_range_id,
                         mac_address_range.id)
        self.assertEqual(saved_mac.address,
                         int(netaddr.EUI("BC:76:4E:20:00:00")))

    def test_allocate_multiple_addresses(self):
        mac_address_range = factory_models.MacAddressRangeFactory(
            cidr="BC:76:4E:00:00:00/24")

        mac_address1 = mac_address_range.allocate_mac()
        mac_address2 = mac_address_range.allocate_mac()

        self.assertEqual(netaddr.EUI(mac_address1.address),
                         netaddr.EUI("BC:76:4E:00:00:00"))
        self.assertEqual(netaddr.EUI(mac_address2.address),
                         netaddr.EUI("BC:76:4E:00:00:01"))

    def test_allocate_mac_address_raises_no_more_addresses_error_if_full(self):
        rng = factory_models.MacAddressRangeFactory(cidr="BC:76:4E:20:0:0/48")

        rng.allocate_mac()

        self.assertRaises(models.NoMoreMacAddressesError, rng.allocate_mac)

    def test_allocate_next_free_mac_from_first_free_range(self):
        two_days_before = datetime.datetime.now() - datetime.timedelta(days=2)
        with unit.StubTime(time=two_days_before):
            factory_models.MacAddressRangeFactory(cidr="BC:76:4E:20:00:00/47")

        factory_models.MacAddressRangeFactory(cidr="BC:76:4E:30:00:00/40")

        mac1 = models.MacAddressRange.allocate_next_free_mac()
        mac2 = models.MacAddressRange.allocate_next_free_mac()
        mac3 = models.MacAddressRange.allocate_next_free_mac()
        mac4 = models.MacAddressRange.allocate_next_free_mac()

        self.assertEqual(netaddr.EUI(mac1.address),
                         netaddr.EUI("BC:76:4E:20:00:00"))
        self.assertEqual(netaddr.EUI(mac2.address),
                         netaddr.EUI("BC:76:4E:20:00:01"))
        self.assertEqual(netaddr.EUI(mac3.address),
                         netaddr.EUI("BC:76:4E:30:00:00"))
        self.assertEqual(netaddr.EUI(mac4.address),
                         netaddr.EUI("BC:76:4E:30:00:01"))

    def test_allocate_next_free_mac_chooses_range_by_created_date_and_id(self):
        self.mock.StubOutWithMock(utils, "generate_uuid")

        def setup_range(cidr, uuid):
            utils.generate_uuid().MultipleTimes().AndReturn(uuid)
            self.mock.ReplayAll()
            rng = factory_models.MacAddressRangeFactory(cidr=cidr)
            self.mock.ResetAll()
            return rng
        today = datetime.datetime.now()
        two_days_before = today - datetime.timedelta(days=2)
        with unit.StubTime(time=two_days_before):
            setup_range("BC:00:4E:20:00:00/47", 0)

        three_days_before = today - datetime.timedelta(days=3)
        with unit.StubTime(time=three_days_before):
            rng_of_uuid_5 = setup_range("AC:76:4E:20:00:00/48", 5)
            rng_of_uuid_2 = setup_range("BC:76:4E:20:00:00/48", 2)
            rng_of_uuid_3 = setup_range("CC:76:4E:20:00:00/48", 3)
            rng_of_uuid_1 = setup_range("DC:76:4E:20:00:00/48", 1)
            rng_of_uuid_4 = setup_range("EC:76:4E:20:00:00/48", 4)
        self.mock.UnsetStubs()

        allocate_mac = models.MacAddressRange.allocate_next_free_mac
        self.assertTrue(rng_of_uuid_1.contains(allocate_mac().address))
        self.assertTrue(rng_of_uuid_2.contains(allocate_mac().address))
        self.assertTrue(rng_of_uuid_3.contains(allocate_mac().address))
        self.assertTrue(rng_of_uuid_4.contains(allocate_mac().address))
        self.assertTrue(rng_of_uuid_5.contains(allocate_mac().address))

    def test_allocate_next_free_mac_raises_error_when_no_more_free_macs(self):
        factory_models.MacAddressRangeFactory(cidr="BC:76:4E:20:0:0/48")
        factory_models.MacAddressRangeFactory(cidr="BC:76:4E:30:0:0/48")

        models.MacAddressRange.allocate_next_free_mac()
        models.MacAddressRange.allocate_next_free_mac()

        self.assertRaises(models.NoMoreMacAddressesError,
                          models.MacAddressRange.allocate_next_free_mac)

    def test_allocate_next_free_mac_goes_to_next_range_on_nomoreaddrserr(self):
        already_full_rng = factory_models.MacAddressRangeFactory(
            cidr="BC:76:4E:20:0:0/48")
        allocatable_rng = factory_models.MacAddressRangeFactory(
            cidr="BC:76:4E:30:0:0/48")

        self.mock.StubOutWithMock(models.MacAddressRange, "find_all")
        models.MacAddressRange.find_all().AndReturn([already_full_rng,
                                                     allocatable_rng])

        self.mock.StubOutWithMock(already_full_rng, "allocate_mac")
        already_full_rng.allocate_mac().AndRaise(
            models.NoMoreMacAddressesError())

        self.mock.StubOutWithMock(allocatable_rng, "allocate_mac")
        expected_mac = models.MacAddress()
        allocatable_rng.allocate_mac().AndReturn(expected_mac)

        self.mock.ReplayAll()

        actual_mac = models.MacAddressRange.allocate_next_free_mac()
        self.assertEqual(expected_mac, actual_mac)

    def test_allocate_mac_retries_on_mac_creation_constraint_failure(self):
        rng = factory_models.MacAddressRangeFactory(cidr="BC:76:4E:20:0:0/24")
        no_of_retries = 3
        self.mock.StubOutWithMock(models.MacAddress, 'create')
        for i in range(no_of_retries - 1):
            self._mock_mac_creation().AndRaise(exception.DBConstraintError())
        expected_mac = models.MacAddress(id=1, address=int(
            netaddr.EUI("BC:76:4E:20:0:0")))

        self._mock_mac_creation().AndReturn(expected_mac)
        self.mock.ReplayAll()

        with unit.StubConfig(mac_allocation_retries=no_of_retries):
            actual_mac = rng.allocate_mac()

        self.assertEqual(actual_mac, expected_mac)

    def test_allocate_mac_raises_error_after_max_retries(self):
        rng = factory_models.MacAddressRangeFactory(cidr="BC:76:4E:20:0:0/24")
        no_of_retries = 3

        self.mock.StubOutWithMock(models.MacAddress, 'create')

        for i in range(no_of_retries):
            self._mock_mac_creation().AndRaise(exception.DBConstraintError())

        self.mock.ReplayAll()

        expected_error_msg = ("Cannot allocate mac address at this time")
        expected_exception = models.ConcurrentAllocationError
        with unit.StubConfig(mac_allocation_retries=no_of_retries):
            self.assertRaisesExcMessage(expected_exception,
                                        expected_error_msg,
                                        rng.allocate_mac)

    def test_allocate_mac_raises_nomoreaddrs_if_retries_exceed_capacity(self):
        rng = factory_models.MacAddressRangeFactory(cidr="BC:76:4E:20:0:0/47")
        no_of_retries = 10

        self.mock.StubOutWithMock(models.MacAddress, 'create')

        for i in range(rng.length()):
            self._mock_mac_creation().AndRaise(exception.DBConstraintError())

        self.mock.ReplayAll()

        with unit.StubConfig(mac_allocation_retries=no_of_retries):
            self.assertRaises(models.NoMoreMacAddressesError,
                              rng.allocate_mac)

    def test_mac_allocation_enabled_when_ranges_exist(self):
        factory_models.MacAddressRangeFactory(cidr="BC:76:4E:20:0:0/48")

        self.assertTrue(models.MacAddressRange.mac_allocation_enabled())

    def test_mac_allocation_disabled_when_no_ranges_exist(self):
        self.assertFalse(models.MacAddressRange.mac_allocation_enabled())

    def test_deallocated_macs_are_allocated_again(self):
        rng = factory_models.MacAddressRangeFactory(cidr="BC:76:4E:20:0:0/40")
        mac = rng.allocate_mac()

        mac.delete()

        self.assertEqual(rng.allocate_mac().address, mac.address)

    def test_contains_mac_address(self):
        rng = factory_models.MacAddressRangeFactory(cidr="BC:76:4E:20:0:0/40")

        self.assertTrue(rng.contains("BC:76:4E:20:00:00"))
        self.assertTrue(rng.contains("BC:76:4E:20:00:FF"))
        self.assertFalse(rng.contains("BC:76:4E:20:01:00"))
        self.assertFalse(rng.contains("AA:BB:CC:20:00:00"))

    def test_data(self):
        rng = factory_models.MacAddressRangeFactory(cidr="BC:76:4E:20:0:0/40")
        expected_data = {'cidr': "BC:76:4E:20:0:0/40",
                         'id': rng.id,
                         'created_at': rng.created_at,
                         'updated_at': rng.updated_at,
                         }
        self.assertEqual(expected_data, rng.data())

    def _mock_mac_creation(self):
        return models.MacAddress.create(address=mox.IgnoreArg(),
                                        mac_address_range_id=mox.IgnoreArg())


class TestMacAddress(tests.BaseTest):

    def test_mac_address_in_eui_format(self):
        rng = factory_models.MacAddressRangeFactory(cidr="BC:76:4E:20:0:0/40")
        mac = rng.allocate_mac()

        self.assertIsNotNone(mac)
        self.assertEqual(mac.eui_format, "BC-76-4E-20-00-00")

    def test_mac_address_is_saved_in_int_format(self):
        mac = models.MacAddress.create(address="BC-76-4E-20-00-00")
        self.assertEqual(mac.address, int(netaddr.EUI("BC-76-4E-20-00-00")))

        mac = mac.update(address="BC-76-4E-20-00-01")
        self.assertEqual(mac.address, int(netaddr.EUI("BC-76-4E-20-00-01")))

        mac = mac.update(address=int(netaddr.EUI("BC-76-4E-20-00-02")))
        self.assertEqual(mac.address, int(netaddr.EUI("BC-76-4E-20-00-02")))

    def test_mac_address_is_within_range(self):
        rng = factory_models.MacAddressRangeFactory(cidr="BC:76:4E:20:0:0/40")
        mac = models.MacAddress(address="AA:AA:AA:20:0:0",
                                mac_address_range_id=rng.id)

        self.assertFalse(mac.is_valid())
        self.assertEqual(mac.errors['address'],
                         ["address does not belong to range"])


class TestPolicy(tests.BaseTest):

    def test_create_policy(self):
        factory_models.PolicyFactory(name="new policy", tenant_id="123",
                                     description="desc")

        policy = models.Policy.find_by(name="new policy")

        self.assertEqual(policy.name, "new policy")
        self.assertEqual(policy.description, "desc")
        self.assertEqual(policy.tenant_id, "123")

    def test_validates_presence_of_name(self):
        policy = factory_models.PolicyFactory.build(name="")
        self.assertFalse(policy.is_valid())
        self.assertEqual(policy.errors['name'], ["name should be present"])

    def test_allows_address_not_in_last_ip_octets(self):
        policy = factory_models.PolicyFactory(name="blah")
        # Create Some octet policies
        factory_models.IpOctetFactory(octet=123,
                                      policy_id=policy.id)
        factory_models.IpOctetFactory(octet=124,
                                      policy_id=policy.id)

        self.assertFalse(policy.allows("10.0.0.0/29", "10.0.0.123"))
        self.assertTrue(policy.allows("10.0.0.0/29", "10.0.0.1"))
        self.assertFalse(policy.allows("10.0.0.0/29", "10.0.0.124"))
        self.assertTrue(policy.allows("10.0.0.0/29", "10.124.123.6"))

    def test_allows_addresses_not_in_ip_range(self):
        policy = factory_models.PolicyFactory(name="blah")
        factory_models.IpRangeFactory(offset=0,
                                      length=2,
                                      policy_id=policy.id)
        factory_models.IpRangeFactory(offset=3,
                                      length=2,
                                      policy_id=policy.id)

        self.assertFalse(policy.allows("10.0.0.0/29", "10.0.0.1"))
        self.assertTrue(policy.allows("10.0.0.0/29", "10.0.0.2"))
        self.assertFalse(policy.allows("10.0.0.0/29", "10.0.0.4"))
        self.assertTrue(policy.allows("10.0.0.0/29", "10.0.0.6"))

    def test_unusable_ip_ranges_for_policy(self):
        policy = factory_models.PolicyFactory(name="blah")
        ip_range1 = factory_models.IpRangeFactory(offset=0,
                                                  length=2,
                                                  policy_id=policy.id)
        ip_range2 = factory_models.IpRangeFactory(offset=3,
                                                  length=2,
                                                  policy_id=policy.id)

        self.assertModelsEqual(policy.unusable_ip_ranges,
                               [ip_range1, ip_range2])

    def test_unusable_ip_ranges_are_cached(self):
        self.assertTrue(isinstance(models.Policy.unusable_ip_ranges,
                                   utils.cached_property))

    def test_unusable_ip_octets_for_policy(self):
        policy = factory_models.PolicyFactory(name="blah")
        ip_octet1 = factory_models.IpOctetFactory(octet=123,
                                                  policy_id=policy.id)
        ip_octet2 = factory_models.IpOctetFactory(octet=124,
                                                  policy_id=policy.id)

        self.assertModelsEqual(policy.unusable_ip_octets,
                               [ip_octet1, ip_octet2])

    def test_unusable_ip_octets_are_cached(self):
        self.assertTrue(isinstance(models.Policy.unusable_ip_octets,
                                   utils.cached_property))

    def test_data(self):
        policy = factory_models.PolicyFactory()

        data = policy.data()

        self.assertEqual(data['id'], policy.id)
        self.assertEqual(data['name'], policy.name)
        self.assertEqual(data['description'], policy.description)
        self.assertEqual(data['tenant_id'], policy.tenant_id)
        self.assertEqual(data['created_at'], policy.created_at)
        self.assertEqual(data['updated_at'], policy.updated_at)

    def test_find_all_to_return_all_policies(self):
        policy1 = factory_models.PolicyFactory(name="physically unstable")
        policy2 = factory_models.PolicyFactory(name="host")

        policies = models.Policy.find_all().all()

        self.assertModelsEqual(policies, [policy1, policy2])

    def test_find_ip_range(self):
        policy = factory_models.PolicyFactory(name='infra')
        ip_range = policy.create_unusable_range(offset=10, length=1)
        # Create a noise range
        factory_models.IpRangeFactory(offset=1, length=22)

        self.assertEqual(policy.find_ip_range(ip_range.id), ip_range)

    def test_find_ip_octet(self):
        policy = factory_models.PolicyFactory()
        ip_octet = factory_models.IpOctetFactory(octet=10,
                                                 policy_id=policy.id)
        # Create a noise octet
        factory_models.IpOctetFactory()

        self.assertEqual(policy.find_ip_octet(ip_octet.id), ip_octet)

    def test_find_invalid_ip_range(self):
        policy = factory_models.PolicyFactory(name='infra')
        # Create a noise range
        policy.create_unusable_range(offset=10, length=1)

        self.assertRaises(models.ModelNotFoundError,
                          policy.find_ip_range,
                          ip_range_id="122222")

    def test_create_unusable_ip_range(self):
        policy = factory_models.PolicyFactory(name="BLAH")

        ip_range = policy.create_unusable_range(offset=1, length=2)

        self.assertEqual(ip_range,
                         models.IpRange.find_by(policy_id=policy.id))
        self.assertEqual(ip_range.offset, 1)
        self.assertEqual(ip_range.length, 2)

    def test_delete_to_cascade_delete_ip_ranges(self):
        policy = factory_models.PolicyFactory(name="Blah")
        ip_range1 = factory_models.IpRangeFactory(offset=1, length=2,
                                                  policy_id=policy.id)
        ip_range2 = factory_models.IpRangeFactory(offset=4, length=2,
                                                  policy_id=policy.id)
        noise_ip_range = factory_models.IpRangeFactory()

        ranges = models.IpRange.find_all(policy_id=policy.id).all()
        self.assertModelsEqual(ranges, [ip_range1, ip_range2])
        policy.delete()
        ranges_after_policy_deletion = models.IpRange.find_all(
            policy_id=policy.id).all()
        self.assertTrue(len(ranges_after_policy_deletion) is 0)
        self.assertTrue(models.IpRange.find(noise_ip_range.id) is not None)

    def test_delete_to_cascade_delete_ip_octets(self):
        policy = factory_models.PolicyFactory(name="Blah")
        ip_octet1 = factory_models.IpOctetFactory(octet=2,
                                                  policy_id=policy.id)
        ip_octet2 = factory_models.IpOctetFactory(octet=255,
                                                  policy_id=policy.id)
        noise_ip_octet = factory_models.IpOctetFactory()

        octets = models.IpOctet.find_all(policy_id=policy.id).all()
        self.assertModelsEqual(octets, [ip_octet1, ip_octet2])
        policy.delete()
        octets_after_policy_deletion = models.IpOctet.find_all(
            policy_id=policy.id).all()
        self.assertTrue(len(octets_after_policy_deletion) is 0)
        self.assertTrue(models.IpOctet.find(noise_ip_octet.id) is not None)

    def test_delete_to_update_associated_ip_blocks_policy(self):
        policy = factory_models.PolicyFactory(name="Blah")
        ip_block = factory_models.PrivateIpBlockFactory(policy_id=policy.id)
        noise_ip_block = factory_models.PrivateIpBlockFactory(
            policy_id=factory_models.PolicyFactory().id)

        policy.delete()
        self.assertTrue(models.IpBlock.find(ip_block.id).policy_id is None)
        self.assertTrue(models.IpBlock.find(noise_ip_block.id).policy_id
                        is not None)


class TestIpRange(tests.BaseTest):

    def test_create_ip_range(self):
        policy = factory_models.PolicyFactory(name='blah')
        factory_models.IpRangeFactory(offset=3, length=10,
                                      policy_id=policy.id)

        ip_range = policy.unusable_ip_ranges[0]

        self.assertEqual(ip_range.offset, 3)
        self.assertEqual(ip_range.length, 10)

    def test_before_save_converts_offset_and_length_to_integer(self):
        ip_range = factory_models.IpRangeFactory(offset="10", length="11")

        self.assertEqual(ip_range.offset, 10)
        self.assertEqual(ip_range.length, 11)

    def test_data(self):
        policy = factory_models.PolicyFactory()
        ip_range = factory_models.IpRangeFactory(offset=10, length=3,
                                                 policy_id=policy.id)

        data = ip_range.data()

        self.assertEqual(data['id'], ip_range.id)
        self.assertEqual(data['offset'], 10)
        self.assertEqual(data['length'], 3)
        self.assertEqual(data['policy_id'], policy.id)
        self.assertEqual(data['created_at'], ip_range.created_at)
        self.assertEqual(data['updated_at'], ip_range.updated_at)

    def test_ip_range_offset_is_an_integer(self):
        ip_range = models.IpRange(offset='spdoe', length=10)

        self.assertFalse(ip_range.is_valid())
        self.assertIn('offset should be of type integer',
                      ip_range.errors['offset'])

    def test_ip_range_length_is_an_integer(self):
        ip_range = models.IpRange(offset='23', length='blah')

        self.assertFalse(ip_range.is_valid())
        self.assertTrue('length should be a positive integer' in
                        ip_range.errors['length'])

    def test_ip_range_length_is_a_natural_number(self):
        ip_range = models.IpRange(offset=11, length='-1')

        self.assertFalse(ip_range.is_valid())
        self.assertTrue('length should be a positive integer' in
                        ip_range.errors['length'])

    def test_range_contains_address(self):
        ip_range = factory_models.IpRangeFactory(offset=0, length=1)

        self.assertTrue(ip_range.contains("10.0.0.0/29", "10.0.0.0"))
        self.assertFalse(ip_range.contains("10.0.0.0/29", "10.0.0.1"))

    def test_range_contains_for_reverse_offset(self):
        ip_range1 = factory_models.IpRangeFactory(offset=-3, length=2)
        ip_range2 = factory_models.IpRangeFactory(offset=-3, length=3)

        self.assertTrue(ip_range1.contains("10.0.0.0/29", "10.0.0.5"))
        self.assertFalse(ip_range1.contains("10.0.0.0/29", "10.0.0.7"))
        self.assertTrue(ip_range2.contains("10.0.0.0/29", "10.0.0.7"))


class TestIpOctet(tests.BaseTest):

    def test_before_save_converts_octet_to_integer(self):
        ip_octet = factory_models.IpOctetFactory(octet="123")
        self.assertEqual(ip_octet.octet, 123)

    def test_data(self):
        policy = factory_models.PolicyFactory()
        ip_octet = factory_models.IpOctetFactory(policy_id=policy.id,
                                                 octet=123)

        data = ip_octet.data()

        self.assertEqual(data['id'], ip_octet.id)
        self.assertEqual(data['octet'], 123)
        self.assertEqual(data['policy_id'], policy.id)
        self.assertEqual(data['created_at'], ip_octet.created_at)
        self.assertEqual(data['updated_at'], ip_octet.updated_at)

    def test_applies_to_is_true_if_address_last_octet_matches(self):
        ip_octet = factory_models.IpOctetFactory(octet=123)
        self.assertTrue(ip_octet.applies_to("10.0.0.123"))
        self.assertTrue(ip_octet.applies_to("192.168.0.123"))
        self.assertFalse(ip_octet.applies_to("123.0.0.124"))


class TestNetwork(tests.BaseTest):

    def test_find_when_ip_blocks_for_given_network_exist(self):
        ip_block1 = factory_models.PublicIpBlockFactory(network_id="1",
                                                        tenant_id="123")
        # Create a noise block
        factory_models.PublicIpBlockFactory(network_id="1",
                                            tenant_id="321")

        network = models.Network.find_by(id="1", tenant_id="123")

        self.assertEqual(network.id, "1")
        self.assertEqual(network.ip_blocks, [ip_block1])

    def test_find_when_no_ip_blocks_for_given_network_exist(self):
        # Create a noise block
        factory_models.PublicIpBlockFactory(network_id="9999")

        self.assertRaises(models.ModelNotFoundError,
                          models.Network.find_by,
                          id="1")

    def test_find_or_create_when_no_ip_blocks_for_given_network_exist(self):
        # Create a noise block
        factory_models.PublicIpBlockFactory(network_id="9999")

        with unit.StubConfig(default_cidr="10.10.10.0/24"):
            network = models.Network.find_or_create_by(id='1', tenant_id='123')

        self.assertEqual(network.id, '1')
        self.assertEqual(len(network.ip_blocks), 1)
        self.assertEqual(network.ip_blocks[0].cidr, "10.10.10.0/24")
        self.assertEqual(network.ip_blocks[0].tenant_id, '123')
        self.assertEqual(network.ip_blocks[0].network_id, '1')
        self.assertEqual(network.ip_blocks[0].type, 'private')

    def test_find_or_create_raises_err_if_no_default_cidr_and_net_blocks(self):
        # Create a noise block
        factory_models.PublicIpBlockFactory(network_id="9999",
                                            tenant_id="tnt")

        with unit.StubConfig(default_cidr=None):
            self.assertRaisesExcMessage(models.ModelNotFoundError,
                                        "Network 100 not found",
                                        models.Network.find_or_create_by,
                                        id="100",
                                        tenant_id="tnt")

    def test_allocate_ip_to_allocate_both_ipv4_and_ipv6_addresses(self):
        ipv4_block = factory_models.PublicIpBlockFactory(network_id="1",
                                                         cidr="10.0.0.0/24",
                                                         tenant_id="111")
        ipv6_block = factory_models.PublicIpBlockFactory(network_id="1",
                                                         cidr="ff::00/120",
                                                         tenant_id="111")
        network = models.Network.find_by(id="1", tenant_id="111")
        interface = factory_models.InterfaceFactory()
        models.MacAddress.create(interface_id=interface.id,
                                 address="aa:bb:cc:dd:ee:ff")

        allocated_ips = network.allocate_ips(interface=interface)

        allocated_ip_blocks_ids = [ip.ip_block_id for ip in allocated_ips]
        self.assertEqual(len(allocated_ips), 2)
        self.assertItemsEqual(allocated_ip_blocks_ids,
                              [ipv4_block.id, ipv6_block.id])

    def test_allocate_ip_from_first_free_ip_block(self):
        interface = factory_models.InterfaceFactory()
        full_ip_block = factory_models.PublicIpBlockFactory(network_id="1",
                                                            is_full=True)
        free_ip_block = factory_models.PublicIpBlockFactory(network_id="1",
                                                            is_full=False)
        network = models.Network(ip_blocks=[full_ip_block, free_ip_block])
        [allocated_ipv4] = network.allocate_ips(interface=interface)

        ip_address = models.IpAddress.find_by(ip_block_id=free_ip_block.id)
        self.assertEqual(allocated_ipv4, ip_address)

    def test_picks_block_to_allocate_sorted_by_created_date_and_id(self):
        interface = factory_models.InterfaceFactory(tenant_id="tenant_id")
        self.mock.StubOutWithMock(utils, "generate_uuid")

        def setup_block(cidr, uuid):
            utils.generate_uuid().MultipleTimes().AndReturn(uuid)
            self.mock.ReplayAll()
            block = factory_models.IpBlockFactory(cidr=cidr,
                                                  network_id="net",
                                                  tenant_id="tenant_id")
            self.mock.ResetAll()
            return block
        today = datetime.datetime.now()
        two_days_before = today - datetime.timedelta(days=2)
        with unit.StubTime(time=two_days_before):
            setup_block("10.1.1.1/31", 0)

        three_days_before = today - datetime.timedelta(days=3)
        with unit.StubTime(time=three_days_before):
            block_of_uuid_5 = setup_block("20.1.1.1/31", 5)
            block_of_uuid_2 = setup_block("30.1.1.1/31", 2)
            block_of_uuid_3 = setup_block("40.1.1.1/31", 3)
            block_of_uuid_1 = setup_block("50.1.1.1/31", 1)
            block_of_uuid_4 = setup_block("60.1.1.1/31", 4)
        self.mock.UnsetStubs()

        network = models.Network.find_by("net", tenant_id="tenant_id")
        allocate_ip = lambda interface: network.allocate_ips(
            interface=interface)[0].address
        self.assertTrue(block_of_uuid_1.contains(allocate_ip(interface)))
        self.assertTrue(block_of_uuid_2.contains(allocate_ip(interface)))
        self.assertTrue(block_of_uuid_3.contains(allocate_ip(interface)))
        self.assertTrue(block_of_uuid_4.contains(allocate_ip(interface)))
        self.assertTrue(block_of_uuid_5.contains(allocate_ip(interface)))

    def test_allocate_ip_raises_error_when_all_ip_blocks_are_full(self):
        interface = factory_models.InterfaceFactory()
        # Create a full block
        factory_models.PublicIpBlockFactory(network_id="1",
                                            is_full=True,
                                            tenant_id="111")

        network = models.Network.find_by(id="1", tenant_id="111")
        self.assertRaises(exception.NoMoreAddressesError,
                          network.allocate_ips,
                          interface=interface)

    def test_allocate_ip_assigns_given_interface_and_addresses(self):
        factory_models.PublicIpBlockFactory(network_id="1", cidr="10.0.0.0/24")
        block = factory_models.PublicIpBlockFactory(network_id="1",
                                                    cidr="169.0.0.0/24")
        addresses = ["10.0.0.7", "169.0.0.2", "10.0.0.3"]
        network = models.Network.find_by(id="1", tenant_id=block.tenant_id)
        interface = factory_models.InterfaceFactory()

        allocated_ips = network.allocate_ips(interface=interface,
                                             addresses=addresses)

        self.assertItemsEqual([ip.address for ip in allocated_ips], addresses)
        for ip in allocated_ips:
            self.assertEqual(ip.interface_id, interface.id)

    def test_allocate_ip_assigns_given_address_from_its_block(self):
        interface = factory_models.InterfaceFactory()
        ip_block1 = factory_models.PublicIpBlockFactory(network_id="1",
                                                        cidr="10.0.0.0/24")
        ip_block2 = factory_models.PublicIpBlockFactory(network_id="1",
                                                        cidr="20.0.0.0/24")
        network = models.Network(ip_blocks=[ip_block1, ip_block2])

        allocated_ip = network.allocate_ips(addresses=["20.0.0.4"],
                                            interface=interface)[0]

        self.assertEqual(allocated_ip.address, "20.0.0.4")
        self.assertEqual(allocated_ip.ip_block_id, ip_block2.id)

    def test_allocate_ip_ignores_already_allocated_addresses(self):
        interface = factory_models.InterfaceFactory()
        ip_block1 = factory_models.PublicIpBlockFactory(network_id="1",
                                                        cidr="10.0.0.0/24")
        ip_block2 = factory_models.PublicIpBlockFactory(network_id="1",
                                                        cidr="20.0.0.0/24")
        factory_models.IpAddressFactory(ip_block_id=ip_block1.id,
                                        address="10.0.0.0")
        network = models.Network(ip_blocks=[ip_block1, ip_block2])

        allocted_ips = network.allocate_ips(addresses=["10.0.0.0", "20.0.0.0"],
                                            interface=interface)
        self.assertTrue(len(allocted_ips) is 1)
        self.assertEqual(allocted_ips[0].address, "20.0.0.0")

    def test_deallocate_ips(self):
        ip_block1 = factory_models.IpBlockFactory(network_id="1",
                                                  cidr="10.0.0.0/24")
        ip_block2 = factory_models.IpBlockFactory(network_id="1",
                                                  cidr="fe80::/64")

        network = models.Network(id="1", ip_blocks=[ip_block1, ip_block2])
        interface = factory_models.InterfaceFactory()
        ip1 = factory_models.IpAddressFactory(ip_block_id=ip_block1.id,
                                              interface_id=interface.id)
        ip2 = factory_models.IpAddressFactory(ip_block_id=ip_block2.id,
                                              interface_id=interface.id)

        network.deallocate_ips(interface_id=interface.id)

        self.assertTrue(models.IpAddress.get(ip1.id).marked_for_deallocation)
        self.assertTrue(models.IpAddress.get(ip2.id).marked_for_deallocation)

    def test_retrieves_allocated_ips(self):
        ip_block1 = factory_models.IpBlockFactory(network_id="1",
                                                  cidr="10.0.0.0/24")
        ip_block2 = factory_models.IpBlockFactory(network_id="1",
                                                  cidr="20.0.0.0/24")
        interface1 = factory_models.InterfaceFactory()
        interface2 = factory_models.InterfaceFactory()
        ip1 = _allocate_ip(ip_block1, interface=interface1)
        ip2 = _allocate_ip(ip_block1, interface=interface1)
        ip3 = _allocate_ip(ip_block2, interface=interface1)
        # create a noise IP
        _allocate_ip(ip_block2, interface=interface2)

        network = models.Network.find_by(id="1")
        allocated_ips = network.allocated_ips(interface_id=interface1.id)

        self.assertModelsEqual(allocated_ips, [ip1, ip2, ip3])

    def test_find_allocated_ip(self):
        ip_block1 = factory_models.IpBlockFactory(network_id="1",
                                                  cidr="10.0.0.0/24")
        ip_block2 = factory_models.IpBlockFactory(network_id="1",
                                                  cidr="20.0.0.0/24")
        # Create a noise block
        factory_models.IpBlockFactory(network_id="1",
                                      cidr="30.0.0.0/24")
        ip1 = _allocate_ip(ip_block1)
        ip2 = _allocate_ip(ip_block2)
        network = models.Network.find_by(id="1")

        self.assertEqual(network.find_allocated_ip(address=ip1.address), ip1)
        self.assertEqual(network.find_allocated_ip(address=ip2.address), ip2)

    def test_find_allocated_ip_raises_model_not_found_for_invalid_ip(self):
        factory_models.IpBlockFactory(network_id="1",
                                      cidr="10.0.0.0/24")
        network = models.Network.find_by(id="1")
        self.assertRaisesExcMessage(models.ModelNotFoundError,
                                    ("IpAddress with {'address': '10.1.1.1'} "
                                     "for network %s not found" % network.id),
                                    network.find_allocated_ip,
                                    address="10.1.1.1")


class TestInterface(tests.BaseTest):

    def test_find_or_configure_finds_existing_interface(self):
        existing_interface = factory_models.InterfaceFactory(
            vif_id_on_device="11234",
            device_id="huge_instance",
            tenant_id="tnt")

        interface_found = models.Interface.find_or_configure(
            virtual_interface_id="11234",
            device_id="huge_instance",
            tenant_id="tnt")

        self.assertEqual(existing_interface, interface_found)

    def test_find_or_configure_finds_without_device_id(self):
        existing_interface = factory_models.InterfaceFactory(
            vif_id_on_device="11234",
            device_id="huge_instance",
            tenant_id="tnt")

        interface_found = models.Interface.find_or_configure(
            virtual_interface_id="11234",
            tenant_id="tnt")

        self.assertEqual(existing_interface, interface_found)

    def test_find_or_configure_fails_if_vif_exists_for_another_tenant(self):
        factory_models.InterfaceFactory(vif_id_on_device="vif",
                                        device_id="device",
                                        tenant_id="tnt1")

        self.assertRaises(models.InvalidModelError,
                          models.Interface.find_or_configure,
                          virtual_interface_id="vif",
                          tenant_id="tnt2",
                          device_id="device")

    def test_find_or_configure_creates_interface_when_not_found(self):
        interface = models.Interface.find_or_configure(
            virtual_interface_id="new_interface",
            device_id="huge_instance",
            tenant_id="tenant")

        created_interface = models.Interface.find_by(id=interface.id)
        self.assertEqual(interface, created_interface)
        self.assertEqual(created_interface.vif_id_on_device,
                         "new_interface")
        self.assertEqual(created_interface.device_id, "huge_instance")
        self.assertEqual(created_interface.tenant_id, "tenant")

    def test_find_or_configure_allocates_mac_address_for_new_interface(self):
        mac_range = factory_models.MacAddressRangeFactory()
        interface = models.Interface.find_or_configure(
            virtual_interface_id="new_interface",
            tenant_id="tenant")

        mac = models.MacAddress.find_by(mac_address_range_id=mac_range.id)
        self.assertEqual(mac.interface_id, interface.id)

    def test_find_or_configure_allocates_mac_for_given_mac_address(self):
        interface = models.Interface.find_or_configure(
            virtual_interface_id="new_interface",
            tenant_id="tenant",
            mac_address="ab:bc:cd:01:12:23")

        mac = models.MacAddress.find_by(interface_id=interface.id)
        self.assertEqual(mac.eui_format,
                         str(netaddr.EUI("ab:bc:cd:01:12:23")))
        self.assertEqual(mac.address, int(netaddr.EUI("ab:bc:cd:01:12:23")))

    def test_find_or_configure_cant_allocate_mac_if_allocation_disabled(self):
        self.assertFalse(models.MacAddressRange.mac_allocation_enabled())

        interface = models.Interface.find_or_configure(
            virtual_interface_id="new_interface",
            tenant_id="tenant")

        self.assertIsNone(models.MacAddress.get_by(interface_id=interface.id))

    def test_validate_virtual_interface_id_is_unique(self):
        factory_models.InterfaceFactory(vif_id_on_device="iface_id")

        dup_iface = factory_models.InterfaceFactory.build(
            vif_id_on_device="iface_id")

        self.assertFalse(dup_iface.is_valid())
        self.assertEqual(dup_iface.errors['virtual_interface_id'],
                         ["Virtual Interface iface_id already exists"])

    def test_validate_presence_of_tenant_id(self):
        interface = factory_models.InterfaceFactory.build(
            tenant_id=None)

        self.assertFalse(interface.is_valid())
        self.assertEqual(interface.errors['tenant_id'],
                         ["tenant_id should be present"])

    def test_update(self):
        interface = factory_models.InterfaceFactory(device_id="device_id")

        interface.update(device_id="new_device_id")

        self.assertEqual(interface.device_id, "new_device_id")

    def test_delete_removes_mac_address(self):
        interface = factory_models.InterfaceFactory()
        mac_range = factory_models.MacAddressRangeFactory()
        mac = mac_range.allocate_mac(interface_id=interface.id)

        interface.delete()

        self.assertIsNone(models.Interface.get(interface.id))
        self.assertIsNone(models.MacAddress.get(mac.id))

    def test_delete_deallocates_ips_on_interface(self):
        interface = factory_models.InterfaceFactory()
        ip1 = factory_models.IpAddressFactory(interface_id=interface.id)
        ip2 = factory_models.IpAddressFactory(interface_id=interface.id)

        interface.delete()

        self.assertIsNone(models.Interface.get(interface.id))
        self.assertTrue(models.IpAddress.get(ip1.id).locked())
        self.assertTrue(models.IpAddress.get(ip2.id).locked())
        self.assertIsNone(models.IpAddress.get(ip1.id).interface_id)
        self.assertIsNone(models.IpAddress.get(ip2.id).interface_id)

    def test_data(self):
        interface = factory_models.InterfaceFactory()

        data = interface.data()

        self.assertEqual(data['id'], interface.virtual_interface_id)
        self.assertEqual(data['device_id'], interface.device_id)
        self.assertEqual(data['tenant_id'], interface.tenant_id)
        self.assertEqual(data['created_at'], interface.created_at)
        self.assertEqual(data['updated_at'], interface.updated_at)

    def test_mac_address(self):
        interface = factory_models.InterfaceFactory()
        mac = models.MacAddress.create(interface_id=interface.id,
                                       address="ab:bc:cd:12:23:34")

        self.assertEqual(interface.mac_address, mac)

    def test_eui_formatted_mac_address(self):
        interface = factory_models.InterfaceFactory()
        models.MacAddress.create(interface_id=interface.id,
                                 address="ab:bc:cd:12:23:34")

        self.assertEqual(interface.mac_address_eui_format,
                         str(netaddr.EUI("ab-bc-cd-12-23-34")))

    def test_mac_address_eui_format_is_none_when_no_mac_address(self):
        interface = factory_models.InterfaceFactory()

        self.assertIsNone(interface.mac_address_eui_format)

    def test_unix_formatted_mac_address(self):
        interface = factory_models.InterfaceFactory()
        models.MacAddress.create(interface_id=interface.id,
                                 address="ab:bc:cd:12:23:34")

        self.assertEqual(interface.mac_address_unix_format,
                         "AB:BC:CD:12:23:34")

    def test_mac_address_unix_format_is_none_when_no_mac_address(self):
        interface = factory_models.InterfaceFactory()

        self.assertIsNone(interface.mac_address_unix_format)

    def test_ip_addresses(self):
        interface = factory_models.InterfaceFactory()

        ip1 = factory_models.IpAddressFactory(interface_id=interface.id)
        ip2 = factory_models.IpAddressFactory(interface_id=interface.id)
        # Create a noise ip
        factory_models.IpAddressFactory()

        self.assertEqual(len(interface.ip_addresses), 2)
        self.assertModelsEqual(interface.ip_addresses, [ip1, ip2])

    def test_network_plugged_into_is_network_of_ip_configured_on_network(self):
        interface = factory_models.InterfaceFactory()
        net1_block = factory_models.IpBlockFactory(network_id="net1")
        net1_block.allocate_ip(interface)

        self.assertEqual(interface.plugged_in_network_id(), "net1")

    def test_delete_by(self):
        interface1 = factory_models.InterfaceFactory(device_id="instance1")
        net1_block = factory_models.IpBlockFactory(network_id="net1")
        iface1_ip = net1_block.allocate_ip(interface1)
        interface2 = factory_models.InterfaceFactory(device_id="instance1")
        interface3 = factory_models.InterfaceFactory(device_id="instance1")
        # Create a noise interface
        factory_models.InterfaceFactory(device_id="ins")

        models.Interface.delete_by(device_id="instance1")

        [self.assertIsNone(models.Interface.get(iface.id)) for iface in
            [interface1, interface2, interface3]]
        self.assertTrue(models.IpAddress.get(
                        iface1_ip.id).marked_for_deallocation)


class TestAllowedIp(tests.BaseTest):

    def _ip_on_network(self, network_id):
        block = factory_models.IpBlockFactory(
            network_id=network_id)
        return block.allocate_ip(factory_models.InterfaceFactory())

    def _plug_interface_into_network(self, network_id, interface):
        factory_models.IpBlockFactory(
            network_id=network_id).allocate_ip(interface)

    def test_allow_ip_on_an_interface(self):
        interface = factory_models.InterfaceFactory()

        ip_on_interface = factory_models.IpBlockFactory(
            network_id="x").allocate_ip(interface)

        ip1 = self._ip_on_network("x")
        ip2 = self._ip_on_network("x")
        # Create some noise ips
        factory_models.IpAddressFactory()
        factory_models.IpAddressFactory()

        interface.allow_ip(ip1)
        interface.allow_ip(ip2)

        actual_allowed_ips = interface.ips_allowed()
        self.assertModelsEqual(actual_allowed_ips, [ip1, ip2, ip_on_interface])

    def test_disallow_an_ip_on_an_interface(self):
        interface1 = factory_models.InterfaceFactory()
        ip_on_interface1 = factory_models.IpBlockFactory(
            network_id="A").allocate_ip(interface1)
        interface2 = factory_models.InterfaceFactory()
        ip_on_interface2 = factory_models.IpBlockFactory(
            network_id="A").allocate_ip(interface2)

        ip1 = self._ip_on_network("A")
        ip2 = self._ip_on_network("A")
        ip3 = self._ip_on_network("A")
        # Create some noise ips
        self._ip_on_network("A")
        self._ip_on_network("A")
        interface1.allow_ip(ip1)
        interface1.allow_ip(ip2)
        interface1.allow_ip(ip3)
        interface2.allow_ip(ip3)

        interface1.disallow_ip(ip2)
        self.assertModelsEqual(interface1.ips_allowed(),
                               [ip1, ip3, ip_on_interface1])

        interface1.disallow_ip(ip3)
        self.assertModelsEqual(interface1.ips_allowed(),
                               [ip1, ip_on_interface1])
        self.assertModelsEqual(interface2.ips_allowed(),
                               [ip3, ip_on_interface2])

    def test_allocating_ips_allows_the_ip_on_the_interface(self):
        interface = factory_models.InterfaceFactory()
        block = factory_models.IpBlockFactory()

        ip = block.allocate_ip(interface=interface)

        self.assertEqual(interface.ips_allowed(), [ip])

    def test_deallocating_ip_disallows_that_ip_on_interface(self):
        interface = factory_models.InterfaceFactory()
        block = factory_models.IpBlockFactory(network_id="xyz")
        ip = block.allocate_ip(interface=interface)
        other_interface = factory_models.InterfaceFactory()
        block.allocate_ip(interface=other_interface)

        other_interface.allow_ip(ip)

        block.deallocate_ip(ip.address)

        self.assertEqual(interface.ips_allowed(), [])
        self.assertEqual(other_interface.find_allowed_ip(ip.address), ip)

    def test_deallocating_allowed_ip_only_disassociates_from_interface(self):
        interface = factory_models.InterfaceFactory()
        block = factory_models.IpBlockFactory(network_id="net123")
        ip = block.allocate_ip(interface=interface)
        other_interface = factory_models.InterfaceFactory()
        self._plug_interface_into_network("net123", other_interface)
        other_interface.allow_ip(ip)
        current_time = datetime.datetime.now()
        two_days_before = current_time - datetime.timedelta(days=2)

        with unit.StubTime(time=two_days_before):
            block.deallocate_ip(ip.address)
        with unit.StubTime(time=current_time):
            block.delete_deallocated_ips(
                deallocated_by_func=models.deallocated_by_date)

        reloaded_ip = models.IpAddress.find(ip.id)
        self.assertFalse(reloaded_ip.marked_for_deallocation)
        self.assertFalse(reloaded_ip.allocated)
        self.assertIsNone(reloaded_ip.interface_id)

    def test_can_explicitly_allow_allocated_ip_on_same_interface(self):
        interface = factory_models.InterfaceFactory()
        block = factory_models.IpBlockFactory()
        ip = block.allocate_ip(interface=interface)
        interface.allow_ip(ip)

        self.assertEqual(interface.ips_allowed(), [ip])

    def test_if_ip_was_explicitly_allowed_deallocating_doesnt_disallow(self):
        interface = factory_models.InterfaceFactory()
        block = factory_models.IpBlockFactory()
        ip = block.allocate_ip(interface=interface)
        interface.allow_ip(ip)

        ip.deallocate()

        self.assertEqual(interface.ips_allowed(), [ip])

    def test_find_allowed_ip(self):
        interface = factory_models.InterfaceFactory()
        self._plug_interface_into_network("xyz", interface)
        ip1 = self._ip_on_network("xyz")
        ip2 = self._ip_on_network("xyz")
        interface.allow_ip(ip1)
        interface.allow_ip(ip2)

        self.assertEqual(interface.find_allowed_ip(ip1.address), ip1)
        self.assertEqual(interface.find_allowed_ip(ip2.address), ip2)

    def test_find_allowed_ip_raises_model_not_found(self):
        interface = factory_models.InterfaceFactory(
            vif_id_on_device="vif_1")
        self._plug_interface_into_network("AAA", interface)
        ip1 = self._ip_on_network("AAA")
        ip2 = self._ip_on_network("AAA")
        unshared_ip = factory_models.IpAddressFactory()
        interface.allow_ip(ip1)
        interface.allow_ip(ip2)

        self.assertRaisesExcMessage(models.ModelNotFoundError,
                                    _("Ip Address %s hasnt been allowed on "
                                    "interface vif_1") % unshared_ip.address,
                                    interface.find_allowed_ip,
                                    unshared_ip.address)

    def test_cannot_allow_ip_when_interface_is_pluged_into_other_network(self):
        interface_plugged_into_net1 = factory_models.InterfaceFactory(
            vif_id_on_device="viffy")
        net1_block = factory_models.IpBlockFactory(network_id="1")
        net1_block.allocate_ip(interface_plugged_into_net1)
        net2_block = factory_models.IpBlockFactory(network_id="2")
        net2_ip = net2_block.allocate_ip(factory_models.InterfaceFactory())

        err_msg = ("Ip %s cannot be allowed on interface viffy "
                   "as interface is not configured "
                   "for ip's network") % net2_ip.address
        self.assertRaisesExcMessage(models.IpNotAllowedOnInterfaceError,
                                    err_msg,
                                    interface_plugged_into_net1.allow_ip,
                                    net2_ip)

    def test_cannot_allow_ip_if_interface_isnt_plugged_into_any_network(self):
        unplugged_interface = factory_models.InterfaceFactory(
            vif_id_on_device="vif_id")
        ip = factory_models.IpAddressFactory()

        err_msg = ("Ip %s cannot be allowed on interface vif_id "
                   "as interface is not configured "
                   "for ip's network") % ip.address
        self.assertRaisesExcMessage(models.IpNotAllowedOnInterfaceError,
                                    err_msg,
                                    unplugged_interface.allow_ip,
                                    ip)


def _allocate_ip(block, interface=None, **kwargs):
    interface = interface or factory_models.InterfaceFactory()
    return block.allocate_ip(interface=interface, **kwargs)


def _setup_notifier(mock):
        mock.StubOutClassWithMocks(notifier, "NoopNotifier")
        return notifier.NoopNotifier()
