# Copyright (C) 2004,2005 PreludeIDS Technologies. All Rights Reserved.
# Author: Nicolas Delon <nicolas.delon@prelude-ids.com>
#
# This file is part of the Prewikka program.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; see the file COPYING.  If not, write to
# the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.


import sys
import time

from preludedb import *
from prewikka import User, Filter, utils, siteconfig

class DatabaseError(Exception):
    pass



class _DatabaseInvalidError(DatabaseError):
    def __init__(self, resource):
        self._resource = resource

    def __str__(self):
        return "invalid %s '%s'" % (self.type, self._resource)



class DatabaseInvalidUserError(_DatabaseInvalidError):
    type = "user"



class DatabaseInvalidSessionError(_DatabaseInvalidError):
    type = "session"



class DatabaseInvalidFilterError(_DatabaseInvalidError):
    type = "filter"


class DatabaseSchemaError(Exception):
    pass


def get_timestamp(s):
    return s and time.mktime(time.strptime(s, "%Y-%m-%d %H:%M:%S")) or None



class Database:
    required_version = "0.9.11"

    # We reference preludedb_sql_destroy since it might be deleted
    # prior Database.__del__() is called.
    _sql_destroy = preludedb_sql_destroy
    _sql = None

    def __init__(self, config):
        settings = preludedb_sql_settings_new()
        for name, default in (("file", None),
                              ("host", "localhost"),
                              ("port", None),
                              ("name", "prewikka"),
                              ("user", "prewikka"),
                              ("pass", None)):
            value = config.get(name, default)
            if value:
                preludedb_sql_settings_set(settings, name.encode("utf8"), value.encode("utf8"))

        db_type = config.get("type", "mysql")
        self._sql = preludedb_sql_new(db_type.encode("utf8"), settings)

        if config.has_key("log"):
            preludedb_sql_enable_query_logging(self._sql, config["log"].encode("utf8"))

        # check if the database has been created
        try:
            version = self.query("SELECT version FROM Prewikka_Version")[0][0]
        except PreludeDBError, e:
            raise DatabaseSchemaError(unicode(utils.toUnicode(e)))

        if version != self.required_version:
            d = { "version": version, "reqversion": self.required_version }
            raise DatabaseSchemaError(_("Database schema version %(version)s found when %(reqversion)s was required") % d)

        # We don't want to impose an SQL upgrade script for this specific change,
        # but this can be moved to an SQL script upon the next schema update.
        self.query("UPDATE Prewikka_User_Configuration SET value='n/a' WHERE (name='alert.assessment.impact.completion' OR name='alert.assessment.impact.severity') AND value='none'")

    def __del__(self):
        if self._sql:
            self._sql_destroy(self._sql)

    def queries_from_file(self, filename):
        content = open(filename).read()
        for query in content.split(";"):
            query = query.strip()
            if len(query) > 0:
                self.query(query)

    def query(self, query):
        try:
            _table = preludedb_sql_query(self._sql, query.encode("utf8"))
            if not _table:
                return [ ]

            columns = preludedb_sql_table_get_column_count(_table)
            table = [ ]
            while True:
                _row = preludedb_sql_table_fetch_row(_table)
                if not _row:
                    break

                row = [ ]
                table.append(row)
                for col in range(columns):
                    _field = preludedb_sql_row_fetch_field(_row, col)
                    if _field:
                        row.append(utils.toUnicode(preludedb_sql_field_to_string(_field)))
                    else:
                        row.append(None)

            preludedb_sql_table_destroy(_table)

        except PreludeDBError, e:
            raise PreludeDBError(e.errno)

        return table

    def transaction_start(self):
        preludedb_sql_transaction_start(self._sql)

    def transaction_end(self):
        preludedb_sql_transaction_end(self._sql)

    def transaction_abort(self):
        preludedb_sql_transaction_abort(self._sql)

    def error(self):
        return

    def escape(self, data):
        if data:
            data = data.encode("utf8")

        return utils.toUnicode(preludedb_sql_escape(self._sql, data))

    def datetime(self, t):
        if t is None:
            return "NULL"
        return "'" + utils.time_to_ymdhms(time.localtime(t)) + "'"

    def hasUser(self, login):
        rows = self.query("SELECT login FROM Prewikka_User WHERE login = %s" % self.escape(login))

        return bool(rows)

    def createUser(self, login, email=None):
        self.query("INSERT INTO Prewikka_User (login, email) VALUES (%s,%s)" % \
                   (self.escape(login), self.escape(email)))

    def deleteUser(self, login):
        login = self.escape(login)
        self.transaction_start()
        try:
            self.query("DELETE FROM Prewikka_User WHERE login = %s" % login)
            self.query("DELETE FROM Prewikka_Permission WHERE login = %s" % login)
            self.query("DELETE FROM Prewikka_Session WHERE login = %s" % login)

            rows = self.query("SELECT id FROM Prewikka_Filter WHERE login = %s" % login)
            if len(rows) > 0:
                lst = ", ".join([ id[0] for id in rows ])
                self.query("DELETE FROM Prewikka_Filter_Criterion WHERE Prewikka_Filter_Criterion.id IN (%s)" % lst)

            self.query("DELETE FROM Prewikka_Filter WHERE login = %s" % login)
        except:
            self.transaction_abort()
            raise

        self.transaction_end()

    def getConfiguration(self, login):

        login = self.escape(login)
        rows = self.query("SELECT view, name, value FROM Prewikka_User_Configuration WHERE login = %s" % login)

        config = { }
        for view, name, value in rows:
            if not config.has_key(view):
                config[view] = { }

            if not config[view].has_key(name):
                config[view][name] = value
            else:
                if isinstance(config[view][name], (str, unicode)):
                    config[view][name] = [ config[view][name] ]

                config[view][name] = config[view][name] + [ value ]

        return config

    def getUserLogins(self):
        return map(lambda r: r[0], self.query("SELECT login FROM Prewikka_User"))

    def getUser(self, login):
        return User.User(self, login, self.getLanguage(login), self.getPermissions(login), self.getConfiguration(login))

    def setPassword(self, login, password):
        self.query("UPDATE Prewikka_User SET password=%s WHERE login = %s" % (self.escape(password), self.escape(login)))

    def getPassword(self, login):
        rows = self.query("SELECT login, password FROM Prewikka_User WHERE login = %s" % (self.escape(login)))
        if not rows or rows[0][0] != login:
            raise DatabaseInvalidUserError(login)

        return rows[0][1]

    def hasPassword(self, login):
        return bool(self.query("SELECT password FROM Prewikka_User WHERE login = %s AND password IS NOT NULL" % self.escape(login)))

    def setLanguage(self, login, lang):
        self.query("UPDATE Prewikka_User SET lang=%s WHERE login = %s" % (self.escape(lang), self.escape(login)))

    def getLanguage(self, login):
        rows = self.query("SELECT lang FROM Prewikka_User WHERE login = %s" % (self.escape(login)))
        if len(rows) > 0:
            return rows[0][0]

        return None

    def setPermissions(self, login, permissions):
        self.transaction_start()
        self.query("DELETE FROM Prewikka_Permission WHERE login = %s" % self.escape(login))
        for perm in permissions:
            self.query("INSERT INTO Prewikka_Permission VALUES (%s,%s)" % (self.escape(login), self.escape(perm)))
        self.transaction_end()

    def getPermissions(self, login):
        return map(lambda r: r[0], self.query("SELECT permission FROM Prewikka_Permission WHERE login = %s" % self.escape(login)))

    def createSession(self, sessionid, login, time):
        self.query("INSERT INTO Prewikka_Session VALUES(%s,%s,%s)" %
                   (self.escape(sessionid), self.escape(login), self.datetime(time)))

    def updateSession(self, sessionid, time):
        self.query("UPDATE Prewikka_Session SET time=%s WHERE sessionid=%s" % (self.datetime(time), self.escape(sessionid)))

    def getSession(self, sessionid):
        rows = self.query("SELECT login, time FROM Prewikka_Session WHERE sessionid = %s" % self.escape(sessionid))
        if not rows:
            raise DatabaseInvalidSessionError(sessionid)

        login, t = rows[0]

        return login, get_timestamp(t)

    def deleteSession(self, sessionid):
        self.query("DELETE FROM Prewikka_Session WHERE sessionid = %s" % self.escape(sessionid))

    def deleteExpiredSessions(self, time):
        self.query("DELETE FROM Prewikka_Session WHERE time < %s" % self.datetime(time))

    def getAlertFilterNames(self, login):
        return map(lambda r: r[0], self.query("SELECT name FROM Prewikka_Filter WHERE login = %s" % self.escape(login)))

    def setFilter(self, login, filter):
        if self.query("SELECT name FROM Prewikka_Filter WHERE login = %s AND name = %s" %
                      (self.escape(login), self.escape(filter.name))):
            self.deleteFilter(login, filter.name)

        self.transaction_start()
        self.query("INSERT INTO Prewikka_Filter (login, name, comment, formula) VALUES (%s, %s, %s, %s)" %
                   (self.escape(login), self.escape(filter.name), self.escape(filter.comment), self.escape(filter.formula)))
        id = int(self.query("SELECT MAX(id) FROM Prewikka_Filter")[0][0])
        for name, element in filter.elements.items():
            self.query("INSERT INTO Prewikka_Filter_Criterion (id, name, path, operator, value) VALUES (%d, %s, %s, %s, %s)" %
                       ((id, self.escape(name)) + tuple([ self.escape(e) for e in element ])))
        self.transaction_end()

    def getAlertFilter(self, login, name):
        rows = self.query("SELECT id, comment, formula FROM Prewikka_Filter WHERE login = %s AND name = %s" %
                          (self.escape(login), self.escape(name)))
        if len(rows) == 0:
            return None

        id, comment, formula = rows[0]
        elements = { }
        for element_name, path, operator, value in \
                self.query("SELECT name, path, operator, value FROM Prewikka_Filter_Criterion WHERE id = %d" % int(id)):
            elements[element_name] = path, operator, value

        return Filter.Filter(name, comment, elements, formula)

    def deleteFilter(self, login, name):
        id = long(self.query("SELECT id FROM Prewikka_Filter WHERE login = %s AND name = %s" % (self.escape(login), self.escape(name)))[0][0])
        self.query("DELETE FROM Prewikka_Filter WHERE id = %d" % id)
        self.query("DELETE FROM Prewikka_Filter_Criterion WHERE id = %d" % id)


