import ast
import csv
import logging
import os
import random
import re
import sys
import gitlab
import requests
import types



def check_access(level):
    if level == "OWNER_ACCESS":
        return 50
    elif level == "MAINTAINER_ACCESS":
        return 40
    elif level == "DEVELOPER_ACCESS":
        return 30
    elif level == "REPORTER_ACCESS":
        return 20
    elif level == "GUEST_ACCESS":
        return 10
    else:
        return 0


class DSL:
    def __init__(self):
        self.variables = {}
        self.builds = []
        session = requests.Session()
        session.proxies = {
            "http": "socks5://127.0.0.1:8123",
            "https": "socks5://127.0.0.1:8123",
        }
        # create gl.Gitlab object
        # private token or personal token authentication
        # gl = gitlab.Gitlab("https://gitlab.com", private_token="PJ4AFco59AX8UBgcSFGc")
        self.gl = gitlab.Gitlab(
            "https://137.195.15.106",
            private_token="zkMbJpiVcn6NnNyK13-e",
            session=session,
            ssl_verify=False,
        )

    def fork_of(self, group):
        """
        find forks of a project and add returned results to
        a new key 'results' to group object
        :rtype: object
        """
        try:
            project_id = group["attributes"]["id"]
            logging.info("getting forks of project {}" "".format(project_id))
            project = self.gl.projects.get(project_id)
            group["results"] = project.forks.list()
            self.add_variable(group["var"], group["results"])
        except Exception as e:
            logging.error("request: fork_of to GitLab API failed. error: " + str(e))
            sys.exit(1)

    def add_variable(self, key, value):
        if key not in self.variables:
            self.variables[key] = value
        else:
            logging.error("variable name: {} already exists" "".format(value))

    def relay_peer_feedback(self, action):
        # read csv file and convert to dictionary
        file_name = action["from"] + ".csv"
        if os.path.isfile(file_name):
            csv_file = open(file_name, "r")
            dict_reader = csv.DictReader(csv_file)

            project_issues = {}
            ordered_dict_from_csv = list(dict_reader)[0]
            dict_from_csv = dict(ordered_dict_from_csv)
            for k, v in dict_from_csv.items():
                id_list = ast.literal_eval(v)
                # get open, peer review issues of each project
                for p in id_list:
                    try:
                        project = self.gl.projects.get(p)
                        issues = project.issues.list(
                            search="Peer review", state="opened"
                        )
                        project_issues[p] = issues
                    except Exception as e:
                        logging.error("request to GitLab API failed. error: " + str(e))
                        sys.exit(1)
                for p in id_list:
                    excludes = [p]
                    for k, v in project_issues.items():
                        if k not in excludes:
                            for issue in v:
                                peer_id = int(
                                    re.findall("\d+", issue.attributes["title"])[0]
                                )
                                peer = self.gl.projects.get(peer_id)
                                try:
                                    issue = peer.issues.create(
                                        {
                                            "title": action["attributes"]["title"]
                                                     + " "
                                                     + str(k),
                                            "description": issue.attributes[
                                                "description"
                                            ],
                                        }
                                    )

                                except Exception as e:
                                    logging.error(
                                        "request to GitLab API failed. error: " + str(e)
                                    )
                                    sys.exit(1)
            logging.info("Replaying peer feedback completed.")

    def create_peer_review(self, action):
        if action["from"] in self.variables:
            var = self.variables[action["from"]]
            project_files = {}
            for key, value in var.items():
                # get files from each project
                for p in value:
                    project_id = p
                    try:
                        project = self.gl.projects.get(project_id)
                        file_path = action["attributes"]["file_path"]
                        f = project.files.get(file_path=file_path, ref="master")
                        project_files[project_id] = f
                    except Exception as e:
                        logging.error("request to GitLab API failed. error: " + str(e))
                        sys.exit(1)
                # upload peer's files to the project
                for p in value:
                    project_id = p
                    project = self.gl.projects.get(project_id)
                    excludes = [project_id]
                    for k, v in project_files.items():
                        if k not in excludes:
                            try:
                                # upload file to project
                                uploaded_file = project.upload(
                                    str(k) + "-" + action["attributes"]["file"],
                                    filedata=v.decode(),
                                )
                                issue = project.issues.create(
                                    {
                                        "title": action["attributes"]["title"]
                                                 + " "
                                                 + str(k),
                                        "description": "See the [attached file]({})".format(
                                            uploaded_file["url"]
                                        ),
                                    }
                                )
                                print(issue)
                            except Exception as e:
                                logging.error(
                                    "request to GitLab API failed. error: " + str(e)
                                )
                                sys.exit(1)
            logging.info("peer review issues created")
        else:
            logging.error("variable is invalid")

    def set_peer_group(self, action):
        if action["from"] in self.variables:
            var = self.variables[action["from"]]
            # get list of project ids
            ids = []
            for p in var:
                ids.append(p.attributes["id"])
            size = action["attributes"]["size"]
            # allocate groups
            peer_groups = {}
            i = 1
            for g in self.chunker(ids, size):
                peer_groups["group" + str(i)] = g
                i += 1
            self.variables[action["var"]] = peer_groups
            # save peer group allocation as a csv file
            file_name = action["var"] + ".csv"
            with open(file_name, "w") as f:
                w = csv.DictWriter(f, peer_groups.keys())
                w.writeheader()
                w.writerow(peer_groups)
            logging.info("saved peer group allocation as " + action["var"] + ".csv")
        else:
            logging.error("variable is not valid")

    # from https://stackoverflow.com/questions/434287/what-is-the-most-pythonic-way-to-iterate-over-a-list-in-chunks
    def chunker(self, seq, size):
        return (seq[pos: pos + size] for pos in range(0, len(seq), size))

    def createFile(self, name, file):
        # temporarily save it as a local file
        fileName = name
        f = open(fileName, "wb")
        f.write((file.decode()))
        f.close()

    def send_builds(self, action):
        if action["to"] in self.variables:
            for p in self.variables[action["to"]]:
                # get a random builds from successful builds
                project_id = random.choice(self.builds)
                project = str.gl.projects.get(project_id)
                file_path = action["attributes"]["file_path"].strip()
                try:
                    build = project.files.get(file_path=file_path, ref="master")
                except Exception as e:
                    logging.error(
                        "request: get_files to GitLab API failed. error: " + str(e)
                    )
                    sys.exit(1)
                # temporarily save it as a local file
                fileName = action["attributes"]["file"]
                self.createFile(fileName, build)
                # commit this file to a breaker repo
                data = {
                    "branch": "master",
                    "commit_message": "start breaking this build",
                    "actions": [
                        {
                            "action": "create",
                            "file_path": fileName,
                            "content": open(fileName).read(),
                        }
                    ],
                }
                project_id = p.attributes["id"]
                try:
                    logging.info("sending build to breaker id:" + p.attributes["id"])
                    project = self.gl.projects.get(project_id)
                    commit = project.commits.create(data)
                except Exception as e:
                    logging.error(
                        "request: create_commit to GitLab API failed. error: " + str(e)
                    )
                    sys.exit(1)
                # remove file
                os.remove(fileName)
                # create an issue
                try:
                    logging.info("creating issue to breaker id:" + p.attributes["id"])
                    issue = project.issues.create(
                        {
                            "title": action["attributes"]["title"],
                            "description": action["attributes"]["description"],
                        }
                    )
                except Exception as e:
                    logging.error(
                        "request: create_issue to GitLab API failed. error: " + str(e)
                    )
                    sys.exit(1)

    def create_group(self, action):
        try:
            group = self.gl.groups.create(action["attributes"])
        except Exception as e:
            logging.error(
                "request: create_group to GitLab API failed. error: " + str(e)
            )
            sys.exit(1)

    def report_test_status(self, action):
        to = action['to']
        title = action["attributes"]["title"]
        description = action["attributes"]["description"]
        if to in self.variables:
            for p in self.variables[action["to"]]:
                project_id = p.attributes["id"]
                origin = p.attributes["path"]
                self.create_test_status(project_id, title, description, origin)
        elif self.gl.projects.get(to):
            try:
                p = self.gl.projects.get(to)
                project_id = p.attributes["id"]
                origin = p.attributes["path"]
                self.create_test_status(project_id, title, description, origin)
            except Exception as e:
                logging.error(
                    "request: create_group to GitLab API failed. error: " + str(e)
                )
            sys.exit(1)
        else:
            logging.error("please check if the variable is valid")

    def delete_project(self, action):
        if action['attributes']['id'] in self.variables:
            for p in self.variables[action['attributes']['id']]:
                try:
                    self.gl.projects.delete(p.attributes['id'])
                except Exception as e:
                    logging.error(
                        "request to GitLab API failed. error: " + str(e)
                    )
                sys.exit(1)
        elif self.gl.projects.get(action['attributes']['id']):
            try:
                self.gl.projects.delete(action['attributes']['id'])
            except Exception as e:
                logging.error(
                    "request to GitLab API failed. error: " + str(e)
                )
        else:
            logging.error("please check if the variable is valid")

    def create_test_status(self, project_id, title, description, origin):
        try:
            project = self.gl.projects.get(project_id)
            pipelines = project.pipelines.list()
            if pipelines[0].attributes["status"] == "success":
                self.builds.append(project_id)
            project_origin = self.gl.projects.get(origin)
            issue = project_origin.issues.create(
                {
                    "title": title,
                    "description": description
                                   + ": "
                                   + pipelines[0].attributes["status"],
                }
            )
        except Exception as e:
            logging.error(
                "request: create_commit to GitLab API failed. error: " + str(e)
            )
            sys.exit(1)

    def create_commit(self, action):
        data = {"branch": "master", "commit_message": "", "actions": []}
        to = self.variables[action["to"]]
        print(to)
        if to in self.variables or self.gl.projects.get(to):
            branch = action["attributes"]["branch"]
            commit_message = action["attributes"]["commit_message"]
            file = action["attributes"]["file"]
            file_path = action["attributes"]["file_path"]
            if "," in file:
                # add to action each file and file path
                file_list = [x.strip() for x in file.split(",")]
                file_path_list = [x.strip() for x in file_path.split(",")]
                if len(file_list) == len(file_path_list):
                    data["branch"] = branch
                    data["commit_message"] = commit_message
                    for x in range(len(file_list)):
                        tmp = self.create_data(file_list[x], file_path_list[x])
                        data["actions"].append(tmp)
                else:
                    logging.error("please check each file has corresponding file path")
            else:
                data = {
                    "branch": branch,
                    "commit_message": commit_message,
                    "actions": [
                        {
                            "action": "create",
                            "file_path": file,
                            "content": open(file_path).read(),
                        }
                    ],
                }
            if to in self.variables and isinstance(to, list):
                for p in self.variables[action["to"]]:
                    project_id = p.attributes["id"]
                    try:
                        project = self.gl.projects.get(project_id)
                        commit = project.commits.create(data)
                    except Exception as e:
                        logging.error(
                            "request: create_commit to GitLab API failed. error: " + str(e)
                        )
                        sys.exit(1)
            elif self.gl.projects.get(to):
                project_id = to
                try:
                    project = self.gl.projects.get(project_id)
                    commit = project.commits.create(data)
                except Exception as e:
                    logging.error(
                        "request: create_commit to GitLab API failed. error: " + str(e)
                    )
                    sys.exit(1)
        else:
            logging.error("variable does not exist.")

    def create_data(self, file, path):
        tmp = {
            "action": "create",
            "file_path": file,
            "content": open(path).read(),
        }
        return tmp

    def projects_in_group(self, group):
        try:
            group_id = group["attributes"]["id"]
            logging.info("getting projects in group with id {}" "".format(group_id))
            tmp = self.gl.groups.get(group_id)
            projects = tmp.projects.list()
            group["results"] = projects
            self.add_variable(group["var"], group["results"])
        except Exception as e:
            logging.error(
                "request: projects_in_group to GitLab API failed. error: " + str(e)
            )
            sys.exit(1)

    def fork_project(self, action):
        var = []
        f = self.gl.projects.get(action['attributes']['id'])
        if action["attributes"]["id"] in self.variables and isinstance(self.variables[action["attributes"]["id"]], list):
            namespace_id = action["attributes"]["namespace_id"]
            visibility = action["attributes"]["visibility"]
            for f in self.variables[action["attributes"]["id"]]:
                pj_id = f.attributes["id"]
                path = str(f.attributes["id"])
                name = str(f.attributes["name"]) + "-" + str(f.attributes["id"])
                fork = self.fork(name, pj_id, namespace_id, visibility, path)
                var.append(fork)
            self.variables[action['var']] = var
        elif f:
            namespace_id = action["attributes"]["namespace_id"]
            visibility = action["attributes"]["visibility"]
            pj_id = f.attributes["id"]
            path = str(f.attributes["id"])
            name = str(f.attributes["name"]) + "-" + str(f.attributes["id"])
            fork = self.fork(name, pj_id, namespace_id, visibility, path)
            self.variables[action['var']] = fork.attributes['id']
        else:
            logging.error("please if the id variable is valid")
        #     add to variable list

    def fork(self, name, pj_id, namespace_id, visibility, path):
        try:
            project = self.gl.projects.get(pj_id)
            fork = project.forks.create(
                {
                    "namespace": namespace_id,
                    "visibility": visibility,
                    "path": path,
                    "name": name,
                }
            )
        except Exception as e:
            logging.error("request: fork to GitLab API failed. error: " + str(e))
            sys.exit(1)
        return fork

    def add_member(self, action):
        """
        add member(s) to a project/group
        """
        pg_id = action["attributes"]["id"]
        user_name = action["attributes"]["user_name"]
        access_level = check_access(action["attributes"]["access_level"])
        if access_level == 0:
            logging.error("access level is invalid")
        else:
            try:
                if action["to"] == "project":
                    project = self.gl.projects.get(pg_id)
                    if "," in user_name:
                        user_id_list = [x.strip() for x in user_name.split(",")]
                        for x in user_id_list:
                            user = self.gl.users.list(username=x)[0]
                            userID = user.attributes["id"]
                            logging.info(
                                "adding user(s) {} to project: {}"
                                "".format(userID, project)
                            )
                            project.members.create(
                                {"user_id": userID, "access_level": access_level}
                            )
                    else:
                        logging.info(
                            "adding user(s) {} to project: {}"
                            "".format(user_name, project)
                        )
                        user = self.gl.users.list(username=user_name)[0]
                        userID = user.attributes["id"]
                        project.members.create(
                            {"user_id": userID, "access_level": access_level}
                        )
                elif action["to"] == "group":
                    group = self.gl.groups.get(pg_id)
                    if "," in user_name:
                        user_id_list = [x.strip() for x in user_name.split(",")]
                        for x in user_id_list:
                            user = self.gl.users.list(username=x)[0]
                            userID = user.attributes["id"]
                            logging.info(
                                "adding user(s) {} to group: {}"
                                "".format(userID, group)
                            )
                            group.members.create(
                                {"user_id": userID, "access_level": access_level}
                            )
                    else:
                        logging.info(
                            "adding user(s) {} to group: {}" "".format(user_name, group)
                        )
                        user = self.gl.users.list(username=user_name)[0]
                        userID = user.attributes["id"]
                        group.members.create(
                            {"user_id": userID, "access_level": access_level}
                        )
            except Exception as e:
                logging.error("request to GitLab API failed. error: " + str(e))
                sys.exit(1)

    def project_with_name(self, group):
        try:
            search = group["attributes"]["search"]
            logging.info("getting projects with name: {}" "".format(search))
            projects = self.gl.projects.list(search=search)
            group["results"] = projects
            self.add_variable(group["var"], group["results"])
        except Exception as e:
            logging.error(
                "request: project_with_name to GitLab API failed. error: " + str(e)
            )
            sys.exit(1)

    def group_with_id(self, group):
        try:
            group_id = group["attributes"]["id"]
            logging.info("getting group with id {}" "".format(group_id))
            group["results"] = self.gl.groups.get(group_id)
            self.add_variable(group["var"], group["results"])
        except Exception as e:
            logging.error(
                "request: group_with_id to GitLab API failed. error: " + str(e)
            )
            sys.exit(1)
