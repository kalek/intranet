# -*- coding: utf-8 -*-
from calendar import monthrange
import datetime
import json
import logging

from babel.core import Locale
from pyramid.view import view_config

from intranet3.models import User, Leave, Holiday, Absence, Late
from intranet3.utils.views import BaseView
from intranet3.utils import idate
from intranet3 import helpers as h


locale = Locale('en', 'US')


@view_config(route_name='employee_table_absences')
class Absences(BaseView):
    WEEKDAYS = locale.days['stand-alone']['narrow']

    def weekday(self, date):
        weekday = date.weekday()
        return self.WEEKDAYS[weekday]

    def necessary_data(self, start, end):
        curr_year = start.year
        days = (end - start).days
        date_range = idate.xdate_range(start, end, group_by_month=True)
        month_range = idate.months_between(start, end)
        month_names = locale.months['format']['wide'].items()
        months = [
            (month_names[m-1][1], monthrange(curr_year, m)[1], m)
            for m in month_range
        ]

        return days, date_range, months

    def get_absences(self, start, end):
        holidays = Holiday.query \
                          .filter(Holiday.date >= start) \
                          .filter(Holiday.date <= end) \
                          .all()
        holidays = [i.date.isoformat() for i in holidays]

        absences = self.session.query(
            Absence.user_id,
            Absence.date_start,
            Absence.date_end,
            Absence.type,
            Absence.remarks,
        )
        absences = absences.filter(Absence.date_start>=start)\
                           .filter(Absence.date_start<=end)

        absences = h.groupby(
            absences,
            lambda x: x[0],
            lambda x: x[1:],
        )

        months = {i: 0 for i in range(1,13)}

        absences_groupped = {}
        td = datetime.timedelta
        for user_id, absences in absences.iteritems():
            if not user_id in absences_groupped:
                absences_groupped[user_id] = {}
            for start, end, type_, remarks in absences:
                month = start.month
                if type_ != 'l4':
                    tmp_start = start
                    while month <= end.month:
                        tmp_end = datetime.date(
                            start.year,
                            month,
                            monthrange(start.year, month)[1]
                        )
                        if month < end.month:
                            length = (tmp_end-tmp_start).days + 1
                        else:
                            length = (end-tmp_start).days + 1
                        # Remove all holidays
                        while tmp_start <= tmp_end and tmp_start <= end:
                            if (tmp_start.isoformat() in holidays or
                                tmp_start.isoweekday() > 5):
                                length -= 1
                            tmp_start += td(days=1)
                        months[month] += length
                        month += 1
                        tmp_start = tmp_start.replace(month=month, day=1)
                length = (end-start).days + 1
                start = start.isoformat()
                absences_groupped[user_id][start] = (length, type_, remarks)

        return absences_groupped, months

    def get_lates(self, start, end):
        lates = self.session.query(Late.user_id, Late.date, Late.explanation)
        lates = lates.filter(Late.date>=start) \
                     .filter(Late.date<=end)

        lates = h.groupby(
            lates,
            lambda x: x[0],
            lambda x: x[1:],
        )

        lates_groupped = {}
        for user_id, lates in lates.iteritems():
            if not user_id in lates_groupped:
                lates_groupped[user_id] = {}
            for date, explanation in lates:
                date = date.strftime('%Y-%m-%d')
                lates_groupped[user_id][date] = explanation

        return lates_groupped

    def get(self):
        year = self.request.GET.get('year')
        year = int(year) if year else datetime.date.today().year
        start = datetime.date(year, 1, 1)
        end = datetime.date(year, 12, 31)
        day_count, date_range, months = self.necessary_data(start, end)
        holidays = Holiday.query \
                          .filter(Holiday.date >= start) \
                          .all()

        users_p = User.query.filter(User.is_not_client()) \
                            .filter(User.is_active==True) \
                            .filter(User.location=='poznan') \
                            .order_by(User.freelancer, User.name).all()
        users_w = User.query.filter(User.is_not_client()) \
                            .filter(User.is_active==True) \
                            .filter(User.location=='wroclaw') \
                            .order_by(User.freelancer, User.name).all()
        user_groups = [
            (u'Poznań', len(users_p)),
            (u'Wrocław', len(users_w)),
        ]
        users_p.extend(users_w)

        absences, absences_months = self.get_absences(start, end)
        lates = self.get_lates(start, end)
        leave_mandated = Leave.get_for_year(start.year)
        leave_used = Leave.get_used_for_year(start.year)

        start_day = dict(
            day=start.day,
            dow=start.weekday(),
        )

        users = [dict(
                      id=str(u.id),
                      name=u.name,
                      leave_mandated=leave_mandated[u.id][0],
                      leave_used=leave_used[u.id],
                      location=u.location,
                     ) for u in users_p]
        users = sorted(
            sorted(
                users,
                key=lambda u: u['leave_mandated']-u['leave_used'],
                reverse=True,
            ),
            key=lambda u: u['location'],
        )

        data = {
            'users': users,
            'userGroups': user_groups,
            'year': start.year,
            'startDay': start_day,
            'dayCount': day_count,
            'months': months,
            'absences': absences,
            'absencesMonths': absences_months,
            'lates': lates,
            'holidays': [h.date.strftime('%Y-%m-%d') for h in holidays],
        }

        return dict(
            data=json.dumps(data, ensure_ascii=False),
            year=start.year,
            v=self,
        )
