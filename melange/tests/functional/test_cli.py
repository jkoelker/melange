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

import melange
from melange import tests
from melange.common import config
from melange.ipam import models
from melange.tests.factories import models as factory_models
from melange.tests import functional


def run_melange_manage(command):
    melange_manage = tests.melange_bin_path('melange-manage')
    config_file = tests.test_config_file()
    return functional.execute("%(melange_manage)s %(command)s "
                              "--config-file=%(config_file)s" % locals())


class TestDBSyncCLI(tests.BaseTest):

    def test_db_sync_executes(self):
        exitcode, out, err = run_melange_manage("db_sync")
        self.assertEqual(exitcode, 0)


class TestDBUpgradeCLI(tests.BaseTest):

    def test_db_upgrade_executes(self):
        exitcode, out, err = run_melange_manage("db_upgrade")
        self.assertEqual(exitcode, 0)


class TestDeleteDeallocatedIps(tests.BaseTest):

    def test_deallocated_ips_get_freed(self):
        block = factory_models.PublicIpBlockFactory()
        ip = factory_models.IpAddressFactory(ip_block_id=block.id)
        block.deallocate_ip(ip.address)

        seconds = config.Config.get('keep_deallocated_ips_for_seconds')
        self._push_back_deallocated_date(ip, seconds)

        script = tests.melange_bin_path('melange-delete-deallocated-ips')
        config_file = tests.test_config_file()
        functional.execute("{0} --config-file={1}".format(script, config_file))

        ip = models.IpAddress.get(ip.id)
        self.assertFalse(ip.allocated)
        self.assertIsNone(ip.interface)
        self.assertIsNone(ip.used_by_tenant_id)

    def _push_back_deallocated_date(self, ip, seconds):
        secs_to_subtract = datetime.timedelta(seconds=int(seconds))
        deallocated_ip = models.IpAddress.find(ip.id)
        new_deallocated_date = deallocated_ip.deallocated_at - secs_to_subtract
        deallocated_ip.update(deallocated_at=(new_deallocated_date))
