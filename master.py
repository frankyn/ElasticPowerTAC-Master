#!/usr/bin/python
import subprocess
import json
import time
from DigitalOceanAPIv2.docean import DOcean


'''
	Master
		* Create droplets with an equal partition of simulations 
		* Once Droplets are created transmit config.json 
		* Run setup script slave.py
		* Run batch-run. 
'''


class ElasticPowerTAC_Master:
	# constructor
	def __init__(self):
		self._config = None

		# Load config
		self.load_config()

		# Create DOcean API Wrapper
		self._docean = DOcean(self._config['api-key'])

	# load_config
	def load_config(self):
		# load from "config.json"
		try:
			config_file = "config.json"
			self._config = None
			with open(config_file,'r') as f:
				self._config = f.read()

			self._config = json.loads(self._config)
		except:
			print('config.json must be defined.')
			exit()

	# Wait creation process
	def wait_until_completed(self,droplet_id):
		# poll until last action is completed.
		while True:
			actions = self._docean.request_droplet_actions(droplet_id)
			# Check all actions are complete
			actions_all_completed = True
			for action in actions['actions']:
				if action['status'] != 'completed':
					actions_all_completed = False
			if not actions_all_completed:
				# If not finished sleep for 1 minute
				time.sleep(30)
			else:
				break

	# setup slave droplets
	def setup_slave_droplets(self):
		# slaves used?
		self._slaves_used = self._config['slaves-used']

		# slave_id container
		self._slaves_id = []

		for x in range(self._slaves_used):
			# Create master with specified image id
			status,new_droplet = self._docean.request_create(
									self._config['slave-name'],
									self._config['slave-image']['region'],
									self._config['slave-image']['size'],
									self._config['slave-image']['id'],
									self._config['slave-image']['ssh_keys'])
			# Check status
			if status != 202:
				print('Unable to create slave droplet')
				exit()

			self._slaves_id.append(new_droplet['droplet']['id'])


		# wait for creation action to finish
		print('Initilized creation process of slaves')

		# Poll actions every minute until all have finished
		for droplet_id in self._slaves_id:
			self.wait_until_completed(droplet_id)

		# Completed
		print('Finished creating Slave Droplets')


	# setup slave environment
	def setup_slave_environment(self):
		# Retrieve IP Address of Master Droplet
		response = self._docean.request_droplets()
		self._slaves = []
		for droplet in response['droplets']:
			if droplet['id'] in self._slaves_id:
				self._slaves.append({"id":droplet['id'],
									 "ip":droplet['networks']['v4'][0]['ip_address']})

		simulation_partition_size = len(self._config['simulations'])//self._slaves_used
		for x in range(len(self._slaves)):
			slave_ip = self._slaves[x]['ip']
			# Setup slave_config dict
			simulation_config = {}
			simulation_config['master-ip'] = self._config['local-ip']
			
			# Partition simulations per slave
			part_start = simulation_partition_size*x
			part_end = simulation_partition_size*x+simulation_partition_size
			simulation_config['simulations'] = self._config['simulations'][part_start:part_end]

			simulation_config_file = 'simulation.config.json'
			

			# Create necessary config.json file for simulation
			with open(simulation_config_file,'w+') as f:
				f.write(json.dumps(simulation_config))

			# Create necessary config.json file for slave
			slave_config = {}
			slave_config['droplet_id'] = self._slaves[x]['id']
			slave_config['api-key'] = self._config['api-key']
			slave_config_file = 'slave.config.json'
			with open(slave_config_file,'w+') as f:
				f.write(json.dumps(slave_config))

			# Clone ElasticPowerTAC-Simulation
			cmd_clone = ['ssh','-o StrictHostKeyChecking=no','log@%s'%slave_ip,
			'git clone --recursive https://github.com/frankyn/ElasticPowerTAC-Simulation.git']
			subprocess.call(cmd_clone)

			# SCP master.config.json to Slave server
			cmd_mcj = ['scp',simulation_config_file, 
				   	   'log@%s:%s'%(slave_ip,'~/ElasticPowerTAC-Simulation/config.json')]
			subprocess.call(cmd_mcj)

			# Clone ElasticPowerTAC-Slave 
			cmd_clone = ['ssh','-o StrictHostKeyChecking=no','root@%s'%slave_ip,
			'git clone --recursive https://github.com/frankyn/ElasticPowerTAC-Slave.git']
			subprocess.call(cmd_clone)

			# SCP master.config.json to Slave server
			cmd_mcj = ['scp',slave_config_file, 
				   	   'root@%s:%s'%(slave_ip,'~/ElasticPowerTAC-Slave/config.json')]
			subprocess.call(cmd_mcj)

			# Run ElasticPowerTAC-Slave
			cmd_run = ['ssh','root@%s'%slave_ip,
					   'screen -A -m -d -S "slave" "python ~/ElasticPowerTAC-Slave/run.py"']
			subprocess.call(cmd_run)



		print("Slaves have been initialized!")



if __name__ == "__main__":
	# Initialize Setup
	elastic_powertac_master = ElasticPowerTAC_Master()
	
	# Setup Master Droplet
	elastic_powertac_master.setup_slave_droplets()

	# Setup Master Environment
	elastic_powertac_master.setup_slave_environment()

	# Setup Done.
	print("Finished master.py")
