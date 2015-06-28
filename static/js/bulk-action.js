/** Deals with displaying the bulk action toolbar. */

// High-level pseudo-namespace for everything in this file.
var bulkAction = {};

/** Allows for setting which set of events we are showing so that we can adapt
 * accordingly.
 @param {String} type: The type of events we are showing. */
bulkAction.setEventType = function(type) {
  bulkAction.eventType = type;
}

/** Manages a set of bulk action checkboxes on the page. */
bulkAction.BulkActionHandler = function() {
  // An array to keep track of all the events that are selected.
  this.selected_ = [];
  // Whether we are showing the actions bar.
  this.barVisible_ = false;
  // A list of actions that we are currently able to perform.
  this.validActions_ = []

  /** Handles a particular change action.
  * @param {Object} event: The event object passed from jQuery.
  */
  this.handleChange = function(event) {
    var name = event.target.name;
    // All of the checkboxes we care about have the name "bulk-select".
    if (name == 'bulk-select') {
      if (event.target.checked) {
        this.addSelected_(event.target);
      } else {
        // If we just uncheked something, the "select all" box shouldn't be
        // checked.
        $('#toggle-all-box').prop('checked', false);

        this.removeSelected_(event.target);
      }

      this.setActionBarVisibility_();
    }
  };

  /** Approves all the events currently selected. */
  this.doApprove = function() {
    if (bulkAction.eventType == 'all_future') {
      if (!this.doAction_('approve', true)) {
        return;
      }

      this.setBadgeText_(null);
      this.toggleChecked(false);
    } else {
      this.doAction_('approve');
    }
  };

  /** Rejects all the events currently selected. */
  this.doReject = function() {
    if (bulkAction.eventType == 'all_future') {
      if (!this.doAction_('notapproved', true)) {
        return;
      }

      this.setBadgeText_('not_approved');
      this.toggleChecked(false);
    } else {
      this.doAction_('notapproved');
    }
  };

  /** Puts all the events currently selected on hold. */
  this.doHold = function() {
    if (bulkAction.eventType == 'pending' ||
        bulkAction.eventType == 'all_future') {
      // For pending events, we need to do this a special way because the events
      // don't dissapear from this view after we've performed the action.
      if (!this.doAction_('onhold', true)) {
        return;
      }

      this.setBadgeText_('onhold');
      this.toggleChecked(false);
    } else {
      this.doAction_('onhold');
    }
  };

  /** Deletes all the events currently selected. */
  this.doDelete = function() {
    this.doAction_('delete');
  };

  /** Check or uncheck everything.
  * @param {Boolean} action: Whether to check or uncheck.
  */
  this.toggleChecked = function(action) {
    this.selected_ = [];
    var outer_this = this;

    $('input').each(function() {
      if (this.name != 'bulk-select') {
        return;
      }

      $(this).prop('checked', action);

      if (action) {
        outer_this.addSelected_(this);
      }
    });

    this.setActionBarVisibility_();
  };


  /** Executes the specified bulk action.
  * @private
  * @param {String} action: The name of the action to perform.
  * @param {Boolean} opt_keep: Specifies whether to keep the events that the
  * action was perfomed on showing afterwards. Defaults to false.
  * @returns: true if it performs the action, false if it doesn't.
  */
  this.doAction_ = function(action, opt_keep) {
    if (!this.barVisible_) {
      return false;
    }
    if (this.validActions_.indexOf(action) < 0) {
      // We can't perform this action.
      return false;
    }

    var properties = {'action': action};

    // Extract the ids of everything selected.
    var selectedIds = this.getDatastoreIds_();

    eventsString = JSON.stringify(selectedIds);
    properties['events'] = eventsString;

    var outer_this = this;
    // Tell the backend to approve them.
    $.post('/bulk_action', properties, function() {
      if (!opt_keep) {
        // Hide everything that is no longer pending.
        for (i = 0; i < selectedIds.length; ++i) {
          // We want to hide the entire row for each event.
          var id = selectedIds[i]  + '-row';
          $('#' + id).fadeOut();
        }

        // Reset selection status.
        outer_this.selected_ = [];
        outer_this.setActionBarVisibility_();
      }
    });

    return true;
  };

  /** Adds a new item to the array of selected items.
  * @private
  * @param {Object} toAdd: The item to add.
  */
  this.addSelected_ = function(toAdd) {
    this.selected_.push(toAdd);
  };

  /** Removes an item from the array of selected items.
  * @private
  * @param {Object} toDelete: The item to remove.
  */
  this.removeSelected_ = function(toDelete) {
    var index = this.selected_.indexOf(toDelete);
    if (index > -1) {
      this.selected_.splice(index, 1);
    }
  };

  /** Sets whether or not the bulk action bar is activated based on what's
   * checked.
   * @private
   */
  this.setActionBarVisibility_ = function() {
    if ((this.selected_.length > 0 && !this.barVisible_) ||
        (!this.selected_.length && this.barVisible_)) {
      this.barVisible_ = !this.barVisible_;

      if (!this.barVisible_) {
        // Hide everything.
        $('#approve').addClass('disabled');
        $('#notapproved').addClass('disabled');
        $('#onhold').addClass('disabled');
        $('#delete').addClass('disabled');
        // The "select all" box should be not be checked if everything is hidden.
        $('#toggle-all-box').prop('checked', this.barVisible_);
      }
      // If stuff should be shown, we'll decide what it is later...
    }

    if (!this.barVisible_) {
      return;
    }

    // Check which buttons we can enable.
    var selectedIds = this.getDatastoreIds_();
    properties = {'events': JSON.stringify(selectedIds)};
    var outer_this = this;
    $.get('/bulk_action_check', properties, function(data) {
      var actions = JSON.parse(data);
      outer_this.validActions_ = actions['valid'];
      var invalid = actions['invalid'];

      for (i = 0; i < outer_this.validActions_.length; ++i) {
        // Make sure these get shown.
        $('#' + outer_this.validActions_[i]).removeClass('disabled');
      }
      for (i = 0; i < invalid.length; ++i) {
        // Make sure these get disabled.
        $('#' + invalid[i]).addClass('disabled');
      }
    });
  };

  /** Extracts the datastore IDs from the elements that are selected.
  * @private
  * @returns: An array of the datastore IDs of everything selected.
  */
  this.getDatastoreIds_ = function() {
    var selectedIds = [];
    for (i = 0; i < this.selected_.length; ++i) {
      var id = this.selected_[i].id
      id = id.replace('-box', '');
      selectedIds.push(id);
    }

    return selectedIds;
  };

  /** Changes the text on the event badges of selected events.
  * @private
  * @param {String} text: The text to change it to, or null. Null erases the
  * badge altogether.
  */
  this.setBadgeText_ = function(text) {
    var selectedIds = this.getDatastoreIds_();

    for (i = 0; i < selectedIds.length; ++i) {
      var badge = $('#' + selectedIds[i] + '-badge');
      if (text == null) {
        badge.fadeOut();
      } else {
        badge.fadeIn();
        badge.text(text);
      }
    }
  };
};

$(document).ready(function() {
  var handler = new bulkAction.BulkActionHandler();

  // Click handler for checkboxes.
  $('input').change(function(event) {
    // We use the anonymous function so that the class gets the correct value
    // for "this".
    handler.handleChange(event);
  });

  // Click handlers for each of the buttons.
  $('#approve').click(function() {
    handler.doApprove();
  });
  $('#notapproved').click(function() {
    handler.doReject();
  });
  $('#onhold').click(function() {
    handler.doHold();
  });
  $('#delete').click(function() {
    handler.doDelete();
  });
  $('#toggle-all').click(function() {
    var action = document.getElementById('toggle-all-box').checked;
    handler.toggleChecked(action);
  });
});
