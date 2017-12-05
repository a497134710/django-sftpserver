=============================
django-sftpserver
=============================

.. image:: https://badge.fury.io/py/django-sftpserver.svg
    :target: https://badge.fury.io/py/django-sftpserver

.. image:: https://travis-ci.org/s1s5/django-sftpserver.svg?branch=master
    :target: https://travis-ci.org/s1s5/django-sftpserver

.. image:: https://codecov.io/gh/s1s5/django-sftpserver/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/s1s5/django-sftpserver

Your project description goes here

Documentation
-------------

The full documentation is at https://django-sftpserver.readthedocs.io.

Quickstart
----------

Install django-sftpserver::

    pip install django-sftpserver

Add it to your `INSTALLED_APPS`:

.. code-block:: python

    INSTALLED_APPS = (
        ...
        'django_sftpserver.apps.DjangoSftpserverConfig',
        ...
    )

Add django-sftpserver's URL patterns:

.. code-block:: python

    from django_sftpserver import urls as django_sftpserver_urls


    urlpatterns = [
        ...
        url(r'^', include(django_sftpserver_urls)),
        ...
    ]

Features
--------

* TODO

Running Tests
-------------

Does the code actually work?

::

    source <YOURVIRTUALENV>/bin/activate
    (myenv) $ pip install tox
    (myenv) $ tox

Credits
-------

Tools used in rendering this package:

*  Cookiecutter_
*  `cookiecutter-djangopackage`_

.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _`cookiecutter-djangopackage`: https://github.com/pydanny/cookiecutter-djangopackage
