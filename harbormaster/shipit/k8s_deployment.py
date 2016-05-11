
# -*- coding: utf-8 -*-

import logging
import re

logger = logging.getLogger(__name__)


class K8SDeployment(object):

    def __init__(self, config=None, project_name=None):
        self.project_name = project_name
        self.config = config

    def get_template(self, service_names=None):
        return self._get_template_or_task(type="taks", service_names=service_names)

    def get_task(self, service_names=None):
        return self._get_template_or_task(type="config", service_names=service_names)

    def _get_template_or_task(self, type="task", service_names=None):
        templates = []
        resolved = []
        for service in self.config.services:
            # group linked services
            if not service_names or service['name'] in service_names:
                if service.get('links'):
                    linked_containers = self._resolve_links(service.get('links'))
                    linked_containers.append(service['name'])
                    resolved += linked_containers
                    if type == 'task':
                        new_template = self._create_task(linked_containers)
                    elif type == 'config':
                        new_template = self._create_template(linked_containers)
                    templates.append(new_template)

        for service in self.ocnfig.services:
            # add any non-linked services
            if not service_names or service['name'] in service_names:
                if service['name'] not in resolved:
                    if type == 'task':
                        new_template = self._create_task([service['name']])
                    elif type == 'config':
                        new_template = self._create_template([service['name']])
                    templates.append(new_template)

        return templates

    @staticmethod
    def _resolve_links(links):
        result = []
        for link in links:
            if ':' in links:
                target = links.split(':')[0]
            else:
                target = link
            result.append(target)
        return result

    def _create_template(self, service_names):
        '''
        Creates a deployment template from a set of services. Each service is a container
        defined within the replication controller.
        '''

        name = "%s-%s" % (self.project_name, service['name'])
        containers = self._services_to_containers(service_names)

        template = dict(
            apiVersion="v1",
            kind="DeploymentConfig",
            metadata=dict(
                name=name,
            ),
            spec=dict(
                template=dict(
                    metadata=dict(
                        labels=dict(
                            app=service['name']
                        )
                    ),
                    spec=dict(
                        containers=containers
                    )
                ),
                replicas=1,
                selector=dict(
                    name=service['name']
                ),
                strategy=dict(
                    type='Rolling'
                )
            )
        )

        return template

    def _create_task(self, service_names):
        '''
        Generates an Ansible playbook task.

        :param service:
        :return:
        '''

        containers = self._services_to_containers(service_names)

        template = dict(
            k8s_deployment=dict(
                project_name=self.project_name,
                service_name=service['name'],
                labels=dict(
                    app=service['name']
                ),
                containers=containers,
                replicas=1,
                strategy='Rolling'
            )
        )

        return template

    def _services_to_containers(self, service_names):
        results = []
        for service in self.config.services:
            if service['name'] in service_names:
                container = dict(name=service['name'])
                for key, value in service.items():
                    if key == 'ports':
                        container['ports'] = self._get_container_ports(value)
                    elif key == 'labels':
                        pass
                    elif key == 'environment':
                        container['env'] = self._expand_env_vars(value)
                    else:
                        container[key] = value
                results.append(container)
        return results

    @staticmethod
    def _get_container_ports(ports):
        '''
        Convert docker ports to list of kube containerPort
        :param ports:
        :type ports: list
        :return:
        '''
        results = []
        for port in ports:
            if ':' in port:
                parts = port.split(':')
                results.append(dict(containerPort=int(parts[1])))
            else:
                results.append(port)
        return results

    @staticmethod
    def _expand_env_vars(env_variables):
        '''
        Turn container environment attribute into kube env dictionary of name/value pairs.

        :param env_variables: container env attribute value
        :type env_variables: dict or list
        :return: dict
        '''
        def f(x):
            return re.sub('^k8s_', '', x, flags=re.I)

        def m(x):
            return re.match('k8s_', x, flags=re.I)

        def r(x, y):
            if m(x):
                return dict(name=f(x), value=self._resolve_resource(y))
            return dict(name=x, value=y)

        results = []
        if isinstance(env_variables, dict):
            for key, value in env_variables.items():
                results.append(r(key, value))
        elif isinstance(env_variables, list):
            for envvar in env_variables:
                parts = envvar.split('=')
                if len(parts) == 1:
                    results.append(dict(name=f(parts[0]), value=None))
                elif len(parts) == 2:
                    results.append(r(parts[0], parts[1]))
        return results

    @staticmethod
    def _resolve_resource(path):
        result = path
        if '/' in path:
            res_type, res_name = path.split('/')
            result = unicode("{{ %s_%s }} " % (res_type, res_name))
        return result
