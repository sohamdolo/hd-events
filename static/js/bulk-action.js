/** Deals with displaying the bulk action toolbar. */

// High-level pseudo-namespace for everything in this file.
var bulkAction = {};

/** Manages a set of bulk action checkboxes on the page. */
bulkAction.BulkActionHandler = function() {
  // An array to keep track of all the events that are selected.
  this.selected_ = [];
  // Whether we are showing the actions bar.
  this.barVisible_ = false;

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
    this.doAction_('approve');
  };

  /** Rejects all the events currently selected. */
  this.doReject = function() {
    this.doAction_('notapproved');
  };

  /** Puts all the events currently selected on hold. */
  this.doHold = function() {
    this.doAction_('onhold', true);

    // Change all the little badges to "onhold".
    for (i = 0; i < this.selected_.length; ++i) {
      var id = this.selected_[i].id.replace('-box', '-badge');
      $('#' + id).text('onhold');
    }

    this.toggleChecked(false);
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
  */
  this.doAction_ = function(action, opt_keep) {
    if (!this.barVisible_) {
      return;
    }

    var properties = {'action': action};

    // Extract the ids of everything selected.
    var selectedIds = [];
    for (i = 0; i < this.selected_.length; ++i) {
      var id = this.selected_[i].id
      id = id.replace('-box', '');
      selectedIds.push(id);
    }

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
      // The state is incorrect, switch it.
      $('#approve').toggleClass('disabled');
      $('#reject').toggleClass('disabled');
      $('#on-hold').toggleClass('disabled');
      $('#delete').toggleClass('disabled');

      this.barVisible_ = !this.barVisible_;

      // The "select all" box should be not be checked if everything is hidden.
      if (!this.barVisible_) {
        $('#toggle-all-box').prop('checked', this.barVisible_);
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
  $('#reject').click(function() {
    handler.doReject();
  });
  $('#on-hold').click(function() {
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
